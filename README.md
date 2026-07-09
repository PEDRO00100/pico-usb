## ⚙️ System Architecture & Operation

This project is a hardware-based security auditing and penetration testing tool (HID Injection Engine) built around the **RP2040** microcontroller. Unlike traditional USB injection scripts that require hardcoding and recompiling firmware for every assessment, this device operates as an autonomous, dynamic execution engine. It reads attack scripts directly from an external MicroSD card and allows instant, on-the-fly selection of up to 16 different payloads via hardware switching.

---

### 1. Hardware & Peripheral Mapping

The PCB layout is engineered for signal integrity, prioritizing short trace lengths for high-speed SPI bus lines while keeping digital control switches isolated. The GPIO pin assignment on the RP2040 is structured as follows:

| Physical Peripheral | RP2040 Pin | System Function / Role | Electrical Logic |
| :--- | :---: | :--- | :--- |
| **Setup Mode Switch (`GP0/DEV`)** | `GP0` | Toggles between Development Mode & Attack Mode | Internal Pull-Up (`GND = Dev`) |
| **DIP Switch (Bit 0 - LSB)** | `GP2` | Binary Payload Selector (`payload1Pin` / `SWD-1`) | Active-Low (`GND = 1`) |
| **DIP Switch (Bit 1)** | `GP3` | Binary Payload Selector (`payload2Pin` / `SWD-2`) | Active-Low (`GND = 1`) |
| **DIP Switch (Bit 2)** | `GP4` | Binary Payload Selector (`payload3Pin` / `SWD-3`) | Active-Low (`GND = 1`) |
| **DIP Switch (Bit 3 - MSB)** | `GP5` | Binary Payload Selector (`payload4Pin` / `SWD-4`) | Active-Low (`GND = 1`) |
| **MicroSD SPI (MISO)** | `GP16` | Data receive from external storage | SPI0 Bus |
| **MicroSD SPI (CS)** | `GP17` | Chip Select / SD card activation | Digital Output |
| **MicroSD SPI (SCK)** | `GP18` | Bus clock synchronization | SPI0 Bus |
| **MicroSD SPI (MOSI)** | `GP19` | Data transmit to external storage | SPI0 Bus |

*(Note: Additional GPIO pins such as `GP22` are routed on the PCB layout for secondary applications or future expansion, but are omitted from active execution loops to streamline automated payload delivery).*

#### 🔘 Onboard Physical Control Buttons
The device incorporates three dedicated tactile buttons for system management and firmware operations:
* **`BOOTSEL` Button:** Connected directly to the RP2040 bootrom interface. Holding this button while plugging the device into a host forces entry into USB Mass Storage bootloader mode for flashing or updating the core CircuitPython firmware (`.uf2` files).
* **`RUN` / `RST` Button:** Triggers a hard electrical reset of the RP2040 microcontroller without needing to physically unplug the USB connector, enabling rapid rebooting after switching payloads.
* **`DEV MODE` Button (`GP0`):** Pulls `GP0` to ground (`GND`). When engaged during boot, it prevents automated payload execution and mounts the internal `CIRCUITPY` drive for safe script editing.

#### 🔌 Dual-Head USB Interface & Protection
The hardware features a versatile **Dual-Head USB architecture**, integrating both **USB-A** and **USB-C** connectors directly onto the PCB edge. This allows native insertion into legacy desktops, modern laptops, servers, and mobile devices without requiring external adapters. 
* **ESD Protection:** The data lines (`D+` / `D-`) include onboard electrical protections and transient voltage suppression to safeguard the microcontroller against static discharges during rapid field insertion.
* **⚠️ Critical Safety Rule:** The dual connectors share the same internal USB data bus. **Never connect both USB-A and USB-C ports simultaneously to two different host devices or power sources**, as this could cause bus contention or electrical back-feeding.

---

### 2. Binary Payload Selector (4-Bit DIP Switch)

To eliminate the need for reprogramming the device between different engagement scenarios, the board features an onboard 4-position DIP switch (`A6H-4101`) operating on **pure binary decoding**.

Each switch pin is configured with internal pull-up resistors (Active-Low logic). Moving a switch to the **ON** position bridges the circuit to Ground (`GND`), which the firmware decodes as a logical `1` for that specific bit position.

```text
Bit 3 (MSB)   Bit 2       Bit 1       Bit 0 (LSB)
  [GP5]       [GP4]       [GP3]       [GP2]
  Value: 8    Value: 4    Value: 2    Value: 1

```

* **Combination `0000` (All OFF):** Executes the default script located at `/sd/payload.dd`.
* **Combinations `0001` through `1111` (1 to 15):** Sums the active bit values in powers of 2 and dynamically routes execution to the numbered script on the MicroSD card (from `/sd/payload1.dd` up to `/sd/payload15.dd`).

---

### 3. Operating Modes & USB Stealth Spoofing

The USB enumeration profile is strictly managed by `boot.py` **before** the target operating system (Windows, macOS, or Linux) initializes the peripheral. The operating mode is governed by the state of the `GP0` tactile button/switch:

#### 🟢 Development Mode (`GP0` connected to GND)

* **Purpose:** Script editing, live debugging, and system maintenance.
* **USB Profile:** Habilitates standard USB Mass Storage (exposing the internal `CIRCUITPY` drive), Serial CDC (REPL console), and HID keyboard interfaces. Automated attack execution is safely bypassed.

#### 🔴 Attack / Stealth Mode (`GP0` floating / Unpressed)

* **Purpose:** Active field auditing and Endpoint Detection & Response (EDR / DLP) evasion.
* **USB Profile:** The firmware executes `storage.disable_usb_drive()`, completely hiding internal Flash memory from the host OS and disabling Serial/MIDI endpoints (`usb_cdc.disable()`, `usb_midi.disable()`).
* **Identity Spoofing:** To prevent triggering vendor-specific blocklists while adhering to safe open-source distribution standards (BYOC - *Bring Your Own Configuration*), the device overrides its hardware descriptors using the open community VID **`0x1209`** (pid.codes) and generic keyboard PID **`0x0001`**:

```python
# Hardware descriptor override defined in boot.py
supervisor.set_usb_identification(
    vid=0x1209,         # Open-Source Community VID (pid.codes)
    pid=0x0001,         # Generic Keyboard PID
    manufacturer="Generic",
    product="USB Keyboard"
)

```

> ⚠️ **Tactical Advantage:** When plugged into a host system in Attack Mode, the operating system **strictly enumerates a generic HID USB Keyboard**. No storage drives are mounted, no COM ports appear in Device Manager, and no Raspberry Pi / Adafruit hardware signatures are exposed.

---

### 4. Asynchronous Execution Engine & Resilience

The core execution engine (`code.py`) is built around asynchronous event loops (`asyncio`). This allows the microcontroller to handle concurrent background tasks—such as button debouncing, filesystem polling, and monitoring host keyboard lock LEDs (Caps/Num/Scroll Lock) for data exfiltration—without causing latency or blocking keystroke injection.

To guarantee field reliability and prevent kernel panics during live deployments, the firmware implements multiple defensive architecture layers:

1. **Zero-RAM Allocation Filesystem Polling:** To check for the presence of payload files on the MicroSD card without fragmenting the microcontroller's limited heap memory, the engine avoids memory-heavy directory listings (`os.listdir()`). Instead, it performs direct, low-overhead FAT32 metadata queries using `os.stat()`.
2. **3-Tier Fallback Routing:** If an indexed script cannot be read, the execution pipeline gracefully degrades through three safety tiers to ensure the assessment does not fail silently:
* *Tier 1:* Attempts to execute the exact binary path selected by the DIP switch (e.g., `/sd/payload5.dd`).
* *Tier 2:* If the target file is missing, it falls back automatically to the standard default script (`/sd/payload.dd`).
* *Tier 3:* If the default script is also missing, it performs an emergency scan of the MicroSD card root and executes the first available `.dd` payload found.


3. **Hardware Kill-Switch:** During the boot sequence, if the engine detects a file named `loot.bin` in the root directory, it immediately aborts all keystroke injection routines to prevent accidental exfiltration overrides or execution loops.

## 💾 Firmware & Software Installation Guide

Setting up the device is divided into two straightforward phases: flashing the base interpreter (CircuitPython) and loading the attack and decoding engine. Once this process is complete, the microcontroller's execution logic will be permanently configured.

---

### Step 1: Installing the Core Engine (CircuitPython)

To enable the RP2040 microcontroller to interpret attack scripts in real time, you must install the base CircuitPython firmware:

1. **Bootloader Mode:** Press and hold the onboard **`BOOTSEL`** physical button while plugging the USB cable into your computer.
2. **RPI-RP2 Drive:** Release the button once plugged in. Your operating system will automatically mount a mass storage drive named `RPI-RP2`.
3. **Flashing:** Download the latest official release of **CircuitPython 10.x** (`.uf2` file format) for the Raspberry Pi Pico / RP2040 and drag the file directly into the `RPI-RP2` drive.
4. **Automatic Reboot:** Once the copy completes, the drive will automatically eject, and the microcontroller will reboot, creating a new flash drive named **`CIRCUITPY`**.

---

### Step 2: Loading the Attack Engine & Dependencies

Once the `CIRCUITPY` drive is available, you must transfer the core operating logic and hardware libraries. Navigate to the `Software/` directory within this repository, which contains the exact system package:

```text
Software/
├── boot.py             # Hardware USB Profile & Stealth Spoofing Manager
├── boot_out.txt        # System boot log (Auto-generated by CircuitPython)
├── code.py             # Asynchronous Core Kernel & Execution Loop
├── duckyinpython.py    # DuckyScript Parser & Payload Execution Engine
├── lib/                # Required CircuitPython libraries (HID, Debouncer, etc.)
├── LICENSE             # GPLv2 License
├── pins.py             # Hardware GPIO Pin Mapping & DIP Switch Config
├── sd/                 # Example payload directory (For external MicroSD card)
└── settings.toml       # Runtime configuration file

```

#### 📦 File Transfer Protocol:

1. **Internal Flash (`CIRCUITPY` drive):**
* Select and copy all core Python scripts (`boot.py`, `code.py`, `duckyinpython.py`, `pins.py`, `settings.toml`, and `LICENSE`).
* **⚠️ CRITICAL - The `lib/` folder:** You **must** copy the entire **`lib/`** directory into the root of the `CIRCUITPY` drive. This folder contains essential drivers (`adafruit_hid`, `adafruit_debouncer`, etc.) required for keystroke injection and tactile button reading.
* *(Note: You can ignore `boot_out.txt`, as the microcontroller will automatically regenerate this log file on its next boot).*


2. **External Storage (MicroSD Card):**
* Take the contents inside the **`sd/`** folder (e.g., your `.dd` payload files) and copy them directly to the root of your FAT32-formatted **MicroSD card**.
* Insert the MicroSD card into the onboard SPI slot (`J3`). When the RP2040 boots, `code.py` will automatically mount this physical card at the `/sd` system path.



---

### Step 3: Access Management & Safe Mode (Critical!)

As soon as the system files are copied over, `boot.py` will take absolute control of the board's USB interfaces on every subsequent boot. It is crucial to understand the following tactical behavior before unplugging the cable:

> 🚨 **AUTOMATIC INJECTION WARNING:**
> From this moment forward, **every time you plug the device into a USB port normally, it will boot in Attack Mode (Stealth Mode)**. This means the `CIRCUITPY` drive will completely disappear from your operating system, and the payload selected via the DIP switch on the MicroSD card **will execute automatically and immediately**.

#### 🛠️ How to re-access the `CIRCUITPY` drive to edit code?

To prevent the attack script from triggering and to mount the internal storage drive back onto your computer (e.g., to debug code or update core scripts), you must engage the hardware safety override:

1. **Press and hold the `DEV MODE` (`GP0`) button** on the board.
2. While holding the button down, **plug the USB cable** into your computer.
3. Once plugged in, you can safely release the button.
4. **Result:** The microcontroller detects the ground connection on pin `GP0`, aborts automated payload execution, and safely exposes the `CIRCUITPY` drive and Serial REPL console on your screen in safe development mode.

## 🛠️ Hardware Compatibility & DIY Protoboard Build

While this project features a custom-designed, dedicated PCB with integrated dual-head USB connectors and ESD protection, the core software suite is **100% compatible with standard, off-the-shelf Raspberry Pi Pico** boards (or any generic RP2040 development board running CircuitPython).

If you are prototyping on a breadboard or building a custom DIY injection tool using an original Raspberry Pi Pico, you can deploy this firmware without modifying a single line of code. You simply need to manually wire the external modules according to the hardware mapping defined in `pins.py`:

### 📌 DIY Wiring Checklist for Standard Pico:
* **MicroSD Card Module:** Wire a 3.3V SPI MicroSD breakout board directly to the RP2040's **SPI0 bus** (`MISO` -> `GP16`, `CS` -> `GP17`, `SCK` -> `GP18`, and `MOSI` -> `GP19`).
* **4-Bit Binary DIP Switch:** Connect four mechanical switches (or simple jumper wires) between ground (`GND`) and pins **`GP2`**, **`GP3`**, **`GP4`**, and **`GP5`**. When closed (grounded), the internal pull-up resistor drops to `0V`, which the software decodes as an active binary `1`.
* **Development Mode Safety Jumper (`GP0`):** You **must** wire a tactile button or jumper wire between **`GP0`** and **`GND`**. This is critical: without this physical override, an off-the-shelf Pico will permanently boot in Stealth Attack Mode, hiding the USB drive and locking you out of the REPL console.

---

## 📂 MicroSD Payload Structure & Binary Mapping

The execution engine searches the root directory of the FAT32-formatted MicroSD card for standard DuckyScript (`.dd`) payload files. To utilize the hardware DIP switch, name your scripts following this exact binary convention:

| DIP Switch State (`SW4` -> `SW1`) | Binary Value | Target Payload Path | Description / Engagement Use Case |
| :---: | :---: | :--- | :--- |
| `OFF` · `OFF` · `OFF` · `OFF` | `0000` (0) | `/sd/payload.dd` | Default fallback / Standard assessment payload |
| `OFF` · `OFF` · `OFF` · `ON`  | `0001` (1) | `/sd/payload1.dd` | Quick reconnaissance / System info enumeration |
| `OFF` · `OFF` · `ON`  · `OFF` | `0010` (2) | `/sd/payload2.dd` | Remote access staging / Reverse shell |
| `...` · `...` · `...` · `...` | `1 to 14`  | `/sd/payload3.dd` to `14.dd` | Custom specialized audit scripts |
| `ON`  · `ON`  · `ON`  · `ON`  | `1111` (15)| `/sd/payload15.dd`| Emergency cleanup / Anti-forensic routine |

> 💡 **Tactical Fallback Note:** If you dial a specific binary combination on the DIP switch (e.g., index `5`) but forget to load `/sd/payload5.dd` onto the MicroSD card, the asynchronous engine will not crash. It automatically downgrades to Tier-2 fallback and executes `/sd/payload.dd`, guaranteeing that your field engagement never fails silently.
