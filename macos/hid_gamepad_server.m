/**
 * @file hid_gamepad_server.m
 * @brief Standalone macOS helper that creates a virtual HID joystick via
 *        IOHIDUserDevice and accepts stick-axis commands over a Unix socket.
 *
 * Build:
 *   clang -framework Foundation -framework IOKit -framework Security \
 *         -o hid_gamepad_server hid_gamepad_server.m
 *
 * Protocol (Unix domain socket):
 *   Each message is exactly 16 bytes: 4 × float (little-endian)
 *     [roll, pitch, yaw, throttle]   each in range -1.0 … +1.0
 *
 * Requirements:
 *   - macOS 12+ on Apple Silicon
 *   - A valid signature and provisioning profile authorizing the restricted
 *     com.apple.developer.hid.virtual.device entitlement
 *
 * Based on the IOHIDUserDevice approach proven in the Lumen project
 * (https://github.com/trollzem/Lumen).
 */

#import <Foundation/Foundation.h>
#import <IOKit/hidsystem/IOHIDUserDevice.h>
#import <Security/SecTask.h>
#import <mach/mach_time.h>
#import <sys/socket.h>
#import <sys/un.h>
#import <signal.h>

// ─── Socket path ────────────────────────────────────────────────────────────────
// Default path; can be overridden with argv[1].
static const char *kDefaultSocketPath = "/tmp/liftoff_gamepad.sock";

// ─── HID Report ─────────────────────────────────────────────────────────────────
// Minimal joystick: 4 signed 16-bit axes (left X/Y, right X/Y).
// No buttons, triggers, or hat — we only need analog sticks for drone control.

typedef struct __attribute__((packed)) {
    uint8_t reportId;       // Always 0x01
    int16_t leftStickX;     // -32768 … 32767
    int16_t leftStickY;
    int16_t rightStickX;
    int16_t rightStickY;
} HIDGamepadReport;         // 9 bytes total

/**
 * HID Report Descriptor — Generic Desktop / Joystick, 4 axes, report ID 0x01.
 *
 * This uses Usage Page 0x01 (Generic Desktop) with Usage 0x04 (Joystick) so
 * that SDL / Unity's old Input system picks it up as a generic joystick rather
 * than routing through the GCController-only code path.
 */
static const uint8_t kHIDReportDescriptor[] = {
    0x05, 0x01,        // Usage Page (Generic Desktop)
    0x09, 0x04,        // Usage (Joystick)
    0xA1, 0x01,        // Collection (Application)
    0x85, 0x01,        //   Report ID (1)

    // --- 4 Stick Axes (16-bit signed each) ---
    0x05, 0x01,        //   Usage Page (Generic Desktop)
    0x09, 0x30,        //   Usage (X)  — Left Stick X
    0x09, 0x31,        //   Usage (Y)  — Left Stick Y
    0x09, 0x32,        //   Usage (Z)  — Right Stick X
    0x09, 0x35,        //   Usage (Rz) — Right Stick Y
    0x16, 0x00, 0x80,  //   Logical Minimum (-32768)
    0x26, 0xFF, 0x7F,  //   Logical Maximum (32767)
    0x75, 0x10,        //   Report Size (16)
    0x95, 0x04,        //   Report Count (4)
    0x81, 0x02,        //   Input (Data, Variable, Absolute)

    0xC0               // End Collection
};

// ─── Globals ────────────────────────────────────────────────────────────────────
static volatile sig_atomic_t gRunning = 1;
static IOHIDUserDeviceRef gHIDDevice = NULL;
static int gListenFd = -1;
static const char *gSocketPath = NULL;

// ─── Signal handler ─────────────────────────────────────────────────────────────
static void handleSignal(int sig) {
    (void)sig;
    gRunning = 0;
}

// ─── Entitlement preflight ─────────────────────────────────────────────────────
static BOOL hasVirtualHIDEntitlement(void) {
    static CFStringRef const entitlementName =
        CFSTR("com.apple.developer.hid.virtual.device");

    SecTaskRef task = SecTaskCreateFromSelf(kCFAllocatorDefault);
    if (!task) {
        NSLog(@"[hid_gamepad_server] Could not inspect this process's "
               "code-signing entitlements (SecTaskCreateFromSelf returned NULL).");
        return NO;
    }

    CFErrorRef error = NULL;
    CFTypeRef value = SecTaskCopyValueForEntitlement(task, entitlementName, &error);
    BOOL entitled = value &&
        CFGetTypeID(value) == CFBooleanGetTypeID() &&
        CFBooleanGetValue((CFBooleanRef)value);

    if (error) {
        NSLog(@"[hid_gamepad_server] Failed to read entitlement %@: %@",
              (__bridge NSString *)entitlementName, (__bridge NSError *)error);
    }

    if (!entitled) {
        NSLog(@"[hid_gamepad_server] Required restricted entitlement is missing "
               "or not true: %@", (__bridge NSString *)entitlementName);
        NSLog(@"[hid_gamepad_server] IOHIDUserDevice creation requires this "
               "entitlement to be authorized by an Apple-issued provisioning "
               "profile and a valid, non-ad-hoc code signature. sudo and SIP "
               "settings do not grant it.");
    }

    if (value) CFRelease(value);
    if (error) CFRelease(error);
    CFRelease(task);
    return entitled;
}

// ─── Create HID device ─────────────────────────────────────────────────────────
static BOOL createHIDDevice(void) {
    NSDictionary *props = @{
        @kIOHIDVendorIDKey:         @(0x1209),  // pid.codes open-source VID
        @kIOHIDProductIDKey:        @(0x5853),
        @kIOHIDManufacturerKey:     @"Liftoff Virtual Gamepad",
        @kIOHIDProductKey:          @"Liftoff Gamepad 0",
        @kIOHIDSerialNumberKey:     @"LIFTOFF-0",
        @kIOHIDTransportKey:        @"USB",
        @kIOHIDReportDescriptorKey: [NSData dataWithBytes:kHIDReportDescriptor
                                                   length:sizeof(kHIDReportDescriptor)],
    };

    gHIDDevice = IOHIDUserDeviceCreateWithProperties(
        kCFAllocatorDefault,
        (__bridge CFDictionaryRef)props,
        0
    );

    if (!gHIDDevice) {
        NSLog(@"[hid_gamepad_server] "
               "IOHIDUserDeviceCreateWithProperties returned NULL.");
        NSLog(@"[hid_gamepad_server] This API does not expose an IOReturn or "
               "CFError for creation failures. Check the macOS unified log for "
               "IOHIDFamily, amfid, and AppleMobileFileIntegrity messages.");
        return NO;
    }

    // Activate on a serial queue for thread safety
    dispatch_queue_attr_t attr = dispatch_queue_attr_make_with_qos_class(
        DISPATCH_QUEUE_SERIAL, QOS_CLASS_USER_INTERACTIVE, 0);
    dispatch_queue_t queue = dispatch_queue_create("com.liftoff.hid.gamepad", attr);
    IOHIDUserDeviceSetDispatchQueue(gHIDDevice, queue);
    IOHIDUserDeviceActivate(gHIDDevice);

    // Send initial neutral-state report
    HIDGamepadReport report = {0};
    report.reportId = 0x01;

    IOReturn result = IOHIDUserDeviceHandleReportWithTimeStamp(
        gHIDDevice, mach_absolute_time(),
        (const uint8_t *)&report, sizeof(report)
    );
    if (result != kIOReturnSuccess) {
        NSLog(@"[hid_gamepad_server] Warning: initial report failed (0x%x)", result);
    }

    NSLog(@"[hid_gamepad_server] Virtual gamepad created successfully.");
    return YES;
}

// ─── Send HID report ────────────────────────────────────────────────────────────
static void sendReport(float roll, float pitch, float yaw, float throttle) {
    if (!gHIDDevice) return;

    // Clamp to -1…1 and scale to int16
    #define CLAMP(v) ((v) < -1.0f ? -1.0f : ((v) > 1.0f ? 1.0f : (v)))
    #define SCALE(v) ((int16_t)(CLAMP(v) * 32767.0f))

    HIDGamepadReport report;
    report.reportId   = 0x01;
    report.leftStickX  = SCALE(yaw);
    report.leftStickY  = SCALE(throttle);
    report.rightStickX = SCALE(roll);
    report.rightStickY = SCALE(pitch);

    #undef CLAMP
    #undef SCALE

    IOHIDUserDeviceHandleReportWithTimeStamp(
        gHIDDevice, mach_absolute_time(),
        (const uint8_t *)&report, sizeof(report)
    );
}

// ─── Cleanup ────────────────────────────────────────────────────────────────────
static void cleanup(void) {
    if (gHIDDevice) {
        // Send neutral state before disconnecting
        HIDGamepadReport report = {0};
        report.reportId = 0x01;
        IOHIDUserDeviceHandleReportWithTimeStamp(
            gHIDDevice, mach_absolute_time(),
            (const uint8_t *)&report, sizeof(report)
        );

        IOHIDUserDeviceCancel(gHIDDevice);
        CFRelease(gHIDDevice);
        gHIDDevice = NULL;
        NSLog(@"[hid_gamepad_server] HID device released.");
    }

    if (gListenFd >= 0) {
        close(gListenFd);
        gListenFd = -1;
    }

    if (gSocketPath) {
        unlink(gSocketPath);
    }
}

// ─── Main ───────────────────────────────────────────────────────────────────────
int main(int argc, const char *argv[]) {
    @autoreleasepool {
        gSocketPath = (argc > 1) ? argv[1] : kDefaultSocketPath;

        // Register signal handlers for clean shutdown
        signal(SIGINT,  handleSignal);
        signal(SIGTERM, handleSignal);

        // 1. Validate authorization and create the virtual HID device
        if (!hasVirtualHIDEntitlement() || !createHIDDevice()) {
            return 1;
        }

        // 2. Set up Unix domain socket
        unlink(gSocketPath);  // Remove stale socket

        gListenFd = socket(AF_UNIX, SOCK_STREAM, 0);
        if (gListenFd < 0) {
            NSLog(@"[hid_gamepad_server] socket() failed: %s", strerror(errno));
            cleanup();
            return 1;
        }

        struct sockaddr_un addr;
        memset(&addr, 0, sizeof(addr));
        addr.sun_family = AF_UNIX;
        strncpy(addr.sun_path, gSocketPath, sizeof(addr.sun_path) - 1);

        if (bind(gListenFd, (struct sockaddr *)&addr, sizeof(addr)) < 0) {
            NSLog(@"[hid_gamepad_server] bind() failed: %s", strerror(errno));
            cleanup();
            return 1;
        }

        if (listen(gListenFd, 1) < 0) {
            NSLog(@"[hid_gamepad_server] listen() failed: %s", strerror(errno));
            cleanup();
            return 1;
        }

        NSLog(@"[hid_gamepad_server] Listening on %s", gSocketPath);
        NSLog(@"[hid_gamepad_server] READY");

        // 3. Accept connections and process messages
        while (gRunning) {
            // Set a timeout so we can check gRunning periodically
            fd_set readfds;
            FD_ZERO(&readfds);
            FD_SET(gListenFd, &readfds);
            struct timeval tv = { .tv_sec = 1, .tv_usec = 0 };

            int sel = select(gListenFd + 1, &readfds, NULL, NULL, &tv);
            if (sel <= 0) continue;

            int clientFd = accept(gListenFd, NULL, NULL);
            if (clientFd < 0) {
                if (gRunning) {
                    NSLog(@"[hid_gamepad_server] accept() failed: %s", strerror(errno));
                }
                continue;
            }

            NSLog(@"[hid_gamepad_server] Client connected.");

            // Read 16-byte messages (4 × float LE) until client disconnects
            while (gRunning) {
                float axes[4];  // roll, pitch, yaw, throttle
                ssize_t bytesRead = 0;
                ssize_t totalNeeded = sizeof(axes);

                // Read exactly 16 bytes (handle partial reads)
                while (bytesRead < totalNeeded) {
                    ssize_t n = read(clientFd, ((uint8_t *)axes) + bytesRead,
                                     totalNeeded - bytesRead);
                    if (n <= 0) {
                        goto client_done;
                    }
                    bytesRead += n;
                }

                sendReport(axes[0], axes[1], axes[2], axes[3]);
            }

        client_done:
            close(clientFd);
            NSLog(@"[hid_gamepad_server] Client disconnected.");
        }

        // 4. Cleanup
        cleanup();
        NSLog(@"[hid_gamepad_server] Shutdown complete.");
        return 0;
    }
}
