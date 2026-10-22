// Derived from MIT-licensed crossover-ffb FFBBridge.swift. See ../../LICENSE.
// Diagnostic adaptation: private mapping, classic-only configuration, JSONL output.
import Foundation
import IOKit.hid
import WheelCore

/// Preserve all evaluator inputs. This remains a sampled diagnostic trace,
/// not a claim to record every 120 Hz DirectInput update or physical torque.
private func effectTrace(_ e: BridgeEffect) -> [String: Any] {
    ["slot": e.slot, "kind": e.kind.rawValue, "playing": e.playing,
     "starts": e.starts, "gain": e.gain, "params": e.params,
     "duration_us": e.durationMicros, "start_delay_us": e.startDelayMicros,
     "coordinates": e.coordinates, "axis_count": e.axisCount, "x_index": e.xIndex,
     "direction": [e.direction.0, e.direction.1], "iterations": e.iterations,
     "has_envelope": e.hasEnvelope, "attack_level": e.attackLevel,
     "attack_us": e.attackMicros, "fade_level": e.fadeLevel, "fade_us": e.fadeMicros,
     "device_elapsed_ms": e.elapsedMilliseconds.map { $0 as Any } ?? NSNull()]
}

/// Owns the wheel while running: forwards HID input into shared memory for the game and
/// plays the game's force-feedback effects on the motor at ~500 Hz. Runs on its own thread.
final class FFBBridge: @unchecked Sendable {
    struct Status: Equatable {
        var running = false
        var wheelConnected = false
        var gameProcessID: UInt32 = 0
        var gameActive = false
        var effectsPlaying = 0
        var output = 0.0
        var input = BridgeInput()
        /// Wheel position before the sensitivity curve, 0…65535.
        var rawSteering: UInt32 = 32768
        var leds: UInt8 = 0
        var message = "Stopped."
        var trueForce = "TrueForce off."
        var telemetry = false
        var tfStreaming = false
    }
    struct TrueForceSettings: Equatable, Sendable {
        var enabled = true
        var strength = 0.6, engine = 0.5, road = 0.6, slip = 0.6
    }
    private static let supportedProducts = [0xc266] // G923 PlayStation/PC, G29

    private let lock = NSLock()
    private var _status = Status()
    private var _strength = 0.8
    private var _allEffects = false
    var allEffects: Bool { get { lock.withLock { _allEffects } } set { lock.withLock { _allEffects = newValue } } }
    private var _reverse = false
    private var _maxForce = 1.0
    var maxForce: Double { get { lock.withLock { _maxForce } } set { lock.withLock { _maxForce = newValue.isFinite ? max(0,min(1,newValue)) : 0 } } }
    private var _motorSign = 1.0
    private var _tfMotorSign = 1.0
    private var _tf = TrueForceSettings()
    private var _wheel = WheelSettings()
    private var _calibrationRequest = false
    private var keepRunning = false
    private var thread: Thread?
    private let finished = DispatchSemaphore(value: 0)
    /// Reports the learned sign and whether it was measured through the TrueForce stream.
    var onCalibrated: (@Sendable (Double?, Bool) -> Void)?

    var status: Status { lock.withLock { _status } }
    var strength: Double { get { lock.withLock { _strength } } set { lock.withLock { _strength = max(0, min(1, newValue)) } } }
    var reverseDirectional: Bool { get { lock.withLock { _reverse } } set { lock.withLock { _reverse = newValue } } }
    var motorSign: Double { get { lock.withLock { _motorSign } } set { lock.withLock { _motorSign = newValue < 0 ? -1 : 1 } } }
    var tfMotorSign: Double { get { lock.withLock { _tfMotorSign } } set { lock.withLock { _tfMotorSign = newValue < 0 ? -1 : 1 } } }
    var trueForce: TrueForceSettings { get { lock.withLock { _tf } } set { lock.withLock { _tf = newValue } } }
    var wheel: WheelSettings { get { lock.withLock { _wheel } } set { lock.withLock { _wheel = newValue } } }
    func requestCalibration() { lock.withLock { _calibrationRequest = true } }

    func start() {
        let alreadyRunning = lock.withLock { () -> Bool in
            if keepRunning { return true }
            keepRunning = true
            return false
        }
        guard !alreadyRunning else { return }
        let thread = Thread { [weak self] in self?.run() }
        thread.name = "crossover-ffb bridge"
        thread.qualityOfService = .userInteractive
        self.thread = thread
        thread.start()
    }

    /// Stops the motor and releases the wheel; waits for the worker (bounded).
    func stop() {
        let wasRunning = lock.withLock { () -> Bool in
            let was = keepRunning
            keepRunning = false
            return was
        }
        if wasRunning { _ = finished.wait(timeout: .now() + 2) }
        thread = nil
    }

    // MARK: worker thread state
    private let sharedPath: String
    init(sharedPath: String) { self.sharedPath = sharedPath }
    private var shared: SharedBridge?
    private var device: IOHIDDevice?
    private var outputLength = 7
    private var input = BridgeInput() // raw from the wheel; games get `published`
    private var published = BridgeInput()
    private var appliedWheel = WheelSettings()
    private var appliedRange = 0
    private var revLights = RevLights()
    private var lastLEDs: UInt8 = 0, lastLEDSend = 0.0
    private var engine = EffectEngine()
    private var position = 0.0, velocity = 0.0, acceleration = 0.0, lastPosition = 0.0, lastTick = 0.0
    private var lastCode: [UInt8] = []
    var sdkForceSign = 1.0
    var sdkForceFile: String?
    private var sdkFileLast = 0.0
    private func publishSDK(_ level: Double) {
        guard let path = sdkForceFile else { return }
        do {
            let data = SDKForceFrame.encode(level: level * sdkForceSign, milliseconds: SharedBridge.nowMilliseconds())
            try data.write(to: URL(fileURLWithPath: path), options: .atomic)
        } catch {
            labLog(["event":"sdk_force_file_failed","error":String(describing:error)])
            lock.withLock { keepRunning = false }
        }
    }
    var crossFFBClassic = false
    var classicSlotUpdates = false
    private var classicForceStream = ClassicForceStream()
    private var lastSend = 0.0
    private var nextScan = 0.0
    private var diagnosticLast = 0.0
    private var writes = 0
    private var writeFailures = 0
    // TrueForce: second HID interface of the same wheel, fed a 4 kHz haptic stream.
    private var tfDevice: IOHIDDevice?
    private var tfWrites=0, tfWriteFailures=0
    private var tfStreaming = false
    private var tfStreamer = TrueForceStreamer()
    private var tfLastPacket = 0.0, tfSampleDebt = 0.0, tfInactiveSince = 0.0
    private let synth = HapticSynth()
    var mesconAudioPort: UInt16?
    private var mesconAudio: MesconAudioReceiver?

    private func update(_ change: (inout Status) -> Void) { lock.withLock { change(&_status) } }

    private func run() {
        defer { finished.signal() }
        if let port=mesconAudioPort {
            do { mesconAudio=try MesconAudioReceiver(port:port) } catch { labLog(["event":"audio_bind_failed","error":String(describing:error)]);return }
        }
        do { shared = try SharedBridge(path: sharedPath) } catch {
            update { $0.message = "Cannot create shared memory: \(error)"; $0.running = false }
            lock.withLock { keepRunning = false }
            return
        }
        update { $0.running = true; $0.message = "Looking for the wheel…" }
        while lock.withLock({ keepRunning }) {
            let now = ProcessInfo.processInfo.systemUptime
            if device == nil, now >= nextScan { nextScan = now + 1; openWheel() }
            // Deliver HID input callbacks. With no wheel there is no source and the call returns at
            // once, so sleep instead of spinning.
            if CFRunLoopRunInMode(.defaultMode, 0.002, false) == .finished { usleep(2000) }
            tick(now: ProcessInfo.processInfo.systemUptime)
        }
        closeWheel(message: "Stopped.")
        update { $0.running = false }
    }

    private func openWheel() {
        let manager = IOHIDManagerCreate(kCFAllocatorDefault, IOOptionBits(kIOHIDOptionsTypeNone))
        IOHIDManagerSetDeviceMatchingMultiple(manager, Self.supportedProducts.map {
            [kIOHIDVendorIDKey: 0x046d, kIOHIDProductIDKey: $0, kIOHIDPrimaryUsagePageKey: 1, kIOHIDPrimaryUsageKey: 4] as CFDictionary
        } as CFArray)
        guard let candidate = (IOHIDManagerCopyDevices(manager) as? Set<IOHIDDevice>)?.first else {
            update { $0.wheelConnected = false; $0.message = "Waiting for a Logitech G923 (PlayStation/PC) or G29 over USB…" }
            return
        }
        let result = IOHIDDeviceOpen(candidate, IOOptionBits(kIOHIDOptionsTypeNone))
        guard result == kIOReturnSuccess else {
            update { $0.message = String(format: "Could not open the wheel (0x%08x). Allow Input Monitoring for crossover-ffb in System Settings › Privacy & Security.", UInt32(bitPattern: result)) }
            return
        }
        device = candidate
        outputLength = max(7, (IOHIDDeviceGetProperty(candidate, kIOHIDMaxOutputReportSizeKey as CFString) as? NSNumber)?.intValue ?? 7)
        let context = Unmanaged.passUnretained(self).toOpaque()
        IOHIDDeviceRegisterInputValueCallback(candidate, { context, _, _, value in
            guard let context else { return }
            Unmanaged<FFBBridge>.fromOpaque(context).takeUnretainedValue().receive(value)
        }, context)
        IOHIDDeviceRegisterRemovalCallback(candidate, { context, _, _ in
            guard let context else { return }
            Unmanaged<FFBBridge>.fromOpaque(context).takeUnretainedValue().closeWheel(message: "Wheel disconnected.")
        }, context)
        IOHIDDeviceScheduleWithRunLoop(candidate, CFRunLoopGetCurrent(), CFRunLoopMode.defaultMode.rawValue)
        input = BridgeInput()
        input.connected = true
        // Seed with current positions; HID only reports changes afterwards.
        for element in IOHIDDeviceCopyMatchingElements(candidate, nil, 0) as? [IOHIDElement] ?? [] {
            let type = IOHIDElementGetType(element)
            guard type == kIOHIDElementTypeInput_Misc || type == kIOHIDElementTypeInput_Axis || type == kIOHIDElementTypeInput_Button else { continue }
            var value = Unmanaged<IOHIDValue>.passUnretained(IOHIDValueCreateWithIntegerValue(kCFAllocatorDefault, element, 0, 0))
            if IOHIDDeviceGetValue(candidate, element, &value) == kIOReturnSuccess { receive(value.takeUnretainedValue()) }
        }
        engine.reset()
        lastCode = []
        classicForceStream.reset()
        if crossFFBClassic {
            for command in CrossFFBClassicProfile.initialization(range: wheel.range, length: outputLength) {
                send(command)
                usleep(CrossFFBClassicProfile.initializationDelayMicroseconds)
            }
            appliedRange = wheel.range
        } else {
            send(LogitechWheelCommand.stopAll(length: outputLength))
            send(LogitechWheelCommand.autocenterOff(length: outputLength))
            appliedRange = 0
        }
        lastLEDs = 0
        send(LogitechWheelCommand.leds(0, length: outputLength))
        // Only the explicit telemetry-emulation candidate opens the TF endpoint.
        if mesconAudioPort != nil { openTrueForce(manager:manager,product:0xc266) }
        if writeFailures == 0 {
            labLog(["event":"input_backend_initialized", "mapping":sharedPath,
                    "physical_playback_confirmed":false])
        }
        update { $0.wheelConnected = true; $0.message = "Wheel ready. Start the game." }
    }

    private func openTrueForce(manager: IOHIDManager, product: Int) {
        tfDevice = nil
        tfStreaming = false
        guard product == 0xc266 || product == 0xc26d || product == 0xc26e else {
            update { $0.trueForce = "TrueForce: this wheel has none (G923 only)." }
            return
        }
        IOHIDManagerSetDeviceMatching(manager, [kIOHIDVendorIDKey: 0x046d, kIOHIDProductIDKey: product,
                                                kIOHIDPrimaryUsagePageKey: 0xfffd, kIOHIDPrimaryUsageKey: 0xfd01] as CFDictionary)
        guard let candidate = (IOHIDManagerCopyDevices(manager) as? Set<IOHIDDevice>)?.first,
              IOHIDDeviceOpen(candidate, IOOptionBits(kIOHIDOptionsTypeNone)) == kIOReturnSuccess else {
            update { $0.trueForce = "TrueForce interface not available; using classic force feedback." }
            return
        }
        tfDevice = candidate
        update { $0.trueForce = "TrueForce ready (starts with the game)." }
    }

    /// Two bring-up passes, then the stream owns the motor until `stopTrueForce`.
    private func startTrueForce(now: Double) -> Bool {
        guard let tfDevice else { return false }
        for _ in 0..<2 {
            for var packet in TrueForceProtocol.initPass() {
                if packet[4] == 0x0e {
                    let bytes=withUnsafeBytes(of:Float(wheel.range).bitPattern.littleEndian,Array.init)
                    for i in 0..<4 { packet[6+i]=bytes[i] }
                }
                guard sendTF(packet, to: tfDevice) else {
                    _=sendTF(TrueForceProtocol.stop(sequence:packet[5] &+ 1),to:tfDevice)
                    IOHIDDeviceClose(tfDevice,IOOptionBits(kIOHIDOptionsTypeNone))
                    update { $0.trueForce = "TrueForce start failed; output stopped." }
                    self.tfDevice = nil
                    return false
                }
            }
        }
        tfStreamer = TrueForceStreamer(sequence: 68)
        tfStreaming = true
        tfLastPacket = now
        tfSampleDebt = 0
        lastCode = []
        classicForceStream.reset()
        update { $0.trueForce = "TrueForce streaming." }
        return true
    }

    private func stopTrueForce() {
        guard tfStreaming else { return }
        tfStreaming = false
        if let tfDevice {
            let zero=sendTF(tfStreamer.silencePacket(),to:tfDevice)
            let stop=sendTF(TrueForceProtocol.stop(sequence:tfStreamer.nextSequence()),to:tfDevice)
            labLog(["event":"tf_cleanup","zero_success":zero,"stop_success":stop,"writes":tfWrites,"failures":tfWriteFailures])
        }
        lastCode = []
        classicForceStream.reset()
        update { $0.trueForce = tfDevice == nil ? "TrueForce off." : "TrueForce ready (starts with the game)." }
    }

    private func sendTF(_ packet: [UInt8], to device: IOHIDDevice) -> Bool {
        let result=packet.withUnsafeBufferPointer {
            IOHIDDeviceSetReport(device, kIOHIDReportTypeOutput, CFIndex(TrueForceProtocol.reportID), $0.baseAddress!, $0.count)
        }
        tfWrites += 1
        if result != kIOReturnSuccess { tfWriteFailures += 1 }
        if result != kIOReturnSuccess || tfWrites % 256 == 0 {
            labLog(["event":"tf_output","writes":tfWrites,"failures":tfWriteFailures,"status":UInt32(bitPattern:result),"packet_type":packet[4]])
        }
        return result == kIOReturnSuccess
    }

    private func closeWheel(message: String) {
        publishSDK(0)
        stopTrueForce()
        if let tfDevice { IOHIDDeviceClose(tfDevice, IOOptionBits(kIOHIDOptionsTypeNone)) }
        tfDevice = nil
        if let device {
            send(LogitechWheelCommand.stopAll(length: outputLength))
            send(LogitechWheelCommand.leds(0, length: outputLength))
            IOHIDDeviceRegisterInputValueCallback(device, nil, nil)
            IOHIDDeviceRegisterRemovalCallback(device, nil, nil)
            IOHIDDeviceUnscheduleFromRunLoop(device, CFRunLoopGetCurrent(), CFRunLoopMode.defaultMode.rawValue)
            IOHIDDeviceClose(device, IOOptionBits(kIOHIDOptionsTypeNone))
        }
        device = nil
        input = BridgeInput()
        published = input
        shared?.publish(input)
        revLights.reset()
        update { $0.wheelConnected = false; $0.output = 0; $0.input = BridgeInput(); $0.message = message }
    }

    private func receive(_ value: IOHIDValue) {
        let element = IOHIDValueGetElement(value)
        guard IOHIDValueGetLength(value) <= 8 else { return }
        let page = IOHIDElementGetUsagePage(element), usage = IOHIDElementGetUsage(element)
        let raw = IOHIDValueGetIntegerValue(value)
        let minimum = IOHIDElementGetLogicalMin(element), maximum = IOHIDElementGetLogicalMax(element)
        if page == 1, usage == 0x39 {
            let direction = HatDirection.decode(raw: raw, minimum: minimum, maximum: maximum, hasNullState: IOHIDElementHasNullState(element))
            let order: [HatDirection] = [.north, .northEast, .east, .southEast, .south, .southWest, .west, .northWest]
            input.hat = order.firstIndex(of: direction).map(UInt32.init) ?? 8
        } else if page == 1, maximum > minimum {
            let clamped = Double(max(minimum, min(maximum, raw)))
            let fraction: Double = (clamped - Double(minimum)) / Double(maximum - minimum)
            let scaled = UInt32((fraction * 65535).rounded())
            // G29/G923 PlayStation report: X wheel, Y clutch, Z accelerator, Rz brake.
            switch usage {
            case 0x30: input.steering = scaled
            case 0x31: input.clutch = scaled
            case 0x32: input.throttle = scaled
            case 0x35: input.brake = scaled
            default: return
            }
        } else if page == 9, (1...25).contains(usage) {
            let bit: UInt32 = 1 << (usage - 1)
            if raw != 0 { input.buttons |= bit } else { input.buttons &= ~bit }
        } else { return }
        published = appliedWheel.apply(to: input)
        shared?.publish(published) // immediately: lowest input latency for the game
    }

    private func tick(now: Double) {
        guard let shared else { return }
        let wheel = lock.withLock { _wheel }
        if wheel != appliedWheel { appliedWheel = wheel; published = wheel.apply(to: input) }
        shared.publish(device == nil ? input : published)
        guard device != nil else { return }
        if appliedRange != wheel.range {
            appliedRange = wheel.range
            send(LogitechWheelCommand.range(wheel.range, length: outputLength))
        }
        let dt = max(0.0005, now - lastTick)
        lastTick = now
        let p = Double(input.steering) / 32767.5 - 1
        let rawVelocity = (p - lastPosition) / dt
        lastPosition = p
        let newVelocity = velocity + 0.2 * (rawVelocity - velocity)
        acceleration += 0.1 * ((newVelocity - velocity) / dt - acceleration)
        velocity = newVelocity
        position = p

        let (strength, reverse, sign, tfSign, tf, calibrate) = lock.withLock { () -> (Double, Bool, Double, Double, TrueForceSettings, Bool) in
            let request = _calibrationRequest
            _calibrationRequest = false
            return (_strength, _reverse, _motorSign, _tfMotorSign, _tf, request)
        }
        if calibrate { calibrateDirection(); return }

        let state = shared.readForce() ?? BridgeForceState()
        let age = Int64(SharedBridge.nowMilliseconds()) - Int64(state.heartbeatMilliseconds)
        let gameActive = state.processID != 0 && age >= -2000 && age < 500 && state.acquired
        let forceLimit = maxForce
        var requestedLevel = 0.0
        var level = 0.0
        let fullEffects = allEffects
        if gameActive && !state.paused && !state.actuatorsOff {
            engine.reverseDirectional = reverse
            requestedLevel = engine.force(fullEffects ? state : ClassicDiagnosticPolicy.directionalOnly(state), wheel: WheelKinematics(position: position, velocity: velocity, acceleration: acceleration), now: now)
            level = ForceOutputPolicy.apply(requestedLevel, gain: strength, limit: forceLimit)
        } else { engine.reset() }
        if !gameActive { revLights.reset() } // a new session may be a different car
        let playing = gameActive ? state.effects.filter(\.playing).count : 0
        if now - diagnosticLast >= 0.1 {
            diagnosticLast = now
            labLog(["event":"force_snapshot", "trace_schema":2,"sampled_not_full_stream":true,"pid":state.processID,"active":gameActive,"age_ms":age,"acquired":state.acquired,"gain":state.deviceGain,"paused":state.paused,"actuators_off":state.actuatorsOff,"output":level,"game_requested":requestedLevel,"force_gain":strength,"force_limit":forceLimit,"game_autocenter":state.autocenter,"tf_streaming":tfStreaming,"conditions_applied":fullEffects,"position":position,"velocity":velocity,"raw_input":["steer":input.steering,"gas":input.throttle,"brake":input.brake,"clutch":input.clutch,"buttons":input.buttons],"published_input":["steer":published.steering,"gas":published.throttle,"brake":published.brake,"clutch":published.clutch,"buttons":published.buttons],"writes":writes,"write_failures":writeFailures,"effects":state.effects.map(effectTrace)])
        }
        if gameActive && !state.paused && wheel.centeringSpring && (playing == 0 || wheel.springInFFBGames) {
            level = max(-1, min(1, level + wheel.centeringForce(position: position, velocity: velocity)))
        }
        level = ForceOutputPolicy.apply(level, gain: 1, limit: forceLimit)
        // TrueForce follows the game session; a short grace period rides out heartbeat jitter.
        if gameActive { tfInactiveSince = now }
        let audioFrame=mesconAudio?.poll(now:now)
        let wantTF = tf.enabled && tfDevice != nil && now - tfInactiveSince < 2 && (audioFrame?.live ?? true)
        if wantTF && !tfStreaming { _ = startTrueForce(now: ProcessInfo.processInfo.systemUptime) }
        if !wantTF && tfStreaming { stopTrueForce() }

        var telemetry: GameTelemetry?
        var maxRpm = 0.0
        if let page = shared.readTelemetry(), page.source == 1 || page.source == 2,
           Int64(SharedBridge.nowMilliseconds()) - Int64(page.unixMilliseconds) < 1000 {
            telemetry = GameTelemetry.acPhysics(page.bytes, evo: page.source == 2)
            maxRpm = Double(page.maxRpm)
        }
        updateRevLights(telemetry: gameActive && wheel.revLights ? telemetry : nil, maxRpm: maxRpm, now: now)
        if sdkForceFile != nil {
            if now - sdkFileLast >= 0.004 { publishSDK(level); sdkFileLast = now }
        } else if tfStreaming, let tfDevice {
            synth.engineGain = tf.engine; synth.roadGain = tf.road; synth.slipGain = tf.slip
            synth.update(gameActive && !state.paused ? telemetry : nil, now: now)
            tfSampleDebt += (now - tfLastPacket) * TrueForceProtocol.sampleRate
            tfLastPacket = now
            let count = max(1, min(TrueForceProtocol.maxNewSamples, Int(tfSampleDebt)))
            tfSampleDebt = max(0, min(Double(TrueForceProtocol.maxNewSamples), tfSampleDebt - Double(count)))
            let samples = audioFrame?.samples ?? synth.render(count: count).map { $0 * tf.strength }
            if !sendTF(tfStreamer.packet(torque: level * tfSign, samples: samples, g923Combined: mesconAudioPort != nil), to: tfDevice) {
                stopTrueForce()
                lock.withLock { keepRunning=false }
                update { $0.trueForce = "TrueForce output failed; bridge stopped. Check wheel power if force persists." }
            }
        } else {
            let code = crossFFBClassic ? CrossFFBClassicProfile.constant(level * sign, length: outputLength) : classicSlotUpdates ? classicForceStream.packet(level * sign, length: outputLength) : LogitechWheelCommand.constant(level * sign, length: outputLength)
            if code != lastCode || now - lastSend > 0.1 {
                send(code)
                lastCode = code
                lastSend = now
            }
        }
        update {
            $0.gameProcessID = state.processID
            $0.gameActive = gameActive
            $0.effectsPlaying = playing
            $0.output = level
            $0.input = published
            $0.rawSteering = input.steering
            $0.leds = lastLEDs
            $0.telemetry = telemetry != nil
            $0.tfStreaming = tfStreaming
            $0.message = gameActive ? "Game connected — force feedback active." : state.processID != 0 && age < 5000 ? "Game seen; waiting for it to acquire the wheel." : "Wheel ready. Start the game."
        }
    }

    /// Short gentle push to learn which motor code turns the wheel toward +X.
    private func calibrateDirection() {
        update { $0.message = "Detecting motor direction — let go of the wheel…" }
        if mesconAudioPort != nil && !tfStreaming {
            guard startTrueForce(now:ProcessInfo.processInfo.systemUptime) else {onCalibrated?(nil,true);return}
        }
        // Separate any initialization movement from the direction measurement.
        let settleDeadline = ProcessInfo.processInfo.systemUptime + 3
        var stableSince = ProcessInfo.processInfo.systemUptime
        var stablePosition = input.steering
        var settled = false
        while ProcessInfo.processInfo.systemUptime < settleDeadline && lock.withLock({ keepRunning }) {
            if tfStreaming,let tfDevice { _=sendTF(tfStreamer.packet(torque:0,samples:[Double](repeating:0,count:8)),to:tfDevice) }
            CFRunLoopRunInMode(.defaultMode, 0.002, false)
            let now = ProcessInfo.processInfo.systemUptime
            if abs(Int(input.steering) - Int(stablePosition)) > 20 { stablePosition = input.steering; stableSince = now }
            if now - stableSince >= 0.3 { settled = true; break }
        }
        labLog(["event":"motor_direction_settled","valid":settled])
        guard settled else { onCalibrated?(nil,false); return }
        let start = input.steering
        let deadline = ProcessInfo.processInfo.systemUptime + 0.2
        let viaTF = tfStreaming
        func push(_ level: Double) {
            if viaTF, let tfDevice { _ = sendTF(tfStreamer.packet(torque: level, samples: [Double](repeating: 0, count: 4)), to: tfDevice) }
            else { send(LogitechWheelCommand.constant(level, length: outputLength)) }
        }
        while ProcessInfo.processInfo.systemUptime < deadline && lock.withLock({ keepRunning }) {
            push(0.12) // the stream needs continuous packets; classic just repeats harmlessly
            CFRunLoopRunInMode(.defaultMode, 0.002, false)
        }
        push(0)
        lastCode = []
        let delta = Int(input.steering) - Int(start)
        labLog(["event":"motor_direction_measurement","start":start,"end":input.steering,"delta":delta,"command":0.12,"duration_ms":200,"via_trueforce":viaTF])
        if abs(delta) < 150 {
            update { $0.message = "Direction test: the wheel did not move. Let go of it and try again." }
            onCalibrated?(nil, viaTF)
        } else {
            let sign: Double = delta > 0 ? 1 : -1
            lock.withLock { if viaTF { _tfMotorSign = sign } else { _motorSign = sign } }
            update { $0.message = viaTF ? "TrueForce motor direction detected." : "Motor direction detected." }
            onCalibrated?(sign, viaTF)
        }
    }

    /// Rev LEDs from telemetry, sent on change (at most every 30 ms); dark without a game.
    private func updateRevLights(telemetry: GameTelemetry?, maxRpm: Double, now: Double) {
        var mask: UInt8 = 0
        if let telemetry, telemetry.engineRunning { mask = revLights.mask(rpm: telemetry.rpm, maxRpm: maxRpm, now: now) }
        guard mask != lastLEDs, now - lastLEDSend > 0.03 else { return }
        send(LogitechWheelCommand.leds(mask, length: outputLength))
        lastLEDs = mask
        lastLEDSend = now
    }

    private func send(_ bytes: [UInt8]) {
        guard sdkForceFile == nil, let device else { return }
        let result = bytes.withUnsafeBufferPointer { IOHIDDeviceSetReport(device, kIOHIDReportTypeOutput, 0, $0.baseAddress!, $0.count) }
        writes += 1
        if result != kIOReturnSuccess { writeFailures += 1; lock.withLock { keepRunning = false } }
        labLog(["event":"classic_hid_output","status":Int64(result),"payload":bytes,"write_count":writes,"physical_playback_confirmed":false])
    }
}
