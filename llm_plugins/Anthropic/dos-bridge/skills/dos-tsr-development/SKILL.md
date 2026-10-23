---
name: dos-tsr-development
description: Design, implement, debug, or review real-mode DOS terminate-and-stay-resident programs with Borland or Turbo C/C++. Use for TSRs, resident utilities, SideKick-style hotkey popups, interrupt-vector hooks, INT 21h function 31h, keep or _dos_keep, safe interrupt chaining, DOS reentrancy, resident memory sizing, TSR detection, or uninstall support. Do not use merely because two ordinary DOS programs should run concurrently; TSRs are interrupt-driven resident software, not general multitasking.
tags: [dos, dosbox-x, tsr, borland, turbo-c, interrupts, real-mode]
---

# DOS TSR Development

Build TSRs as interrupt-driven extensions to a single-tasking DOS guest. Treat
them as fragile systems code: preserve machine state, minimize interrupt work,
and prove ownership before altering interrupt chains or freeing memory.

## Required reference

Read [references/tsr-engineering.md](references/tsr-engineering.md) completely
before writing or changing TSR code. It contains the Borland-specific ABI,
memory, reentrancy, popup, uninstall, and test requirements.

## Workflow

1. Confirm that a TSR is the correct mechanism.
   - Use a TSR for a resident hotkey, software-interrupt service, lightweight
     monitor, or popup accessory that must survive after returning to DOS.
   - Do not use a TSR to simulate threads, run two arbitrary foreground
     programs, or bypass the bridge's serialized command model.
2. Discover the target before designing.
   - Identify DOS version, Borland/Turbo compiler version, memory model, CPU
     target, graphics or text modes, loaded TSRs, and DOS extender use.
   - Prefer real mode. Stop and redesign if the foreground application uses a
     protected-mode extender that virtualizes interrupts or memory.
3. Choose the least invasive activation path.
   - Prefer a private software interrupt for program-to-TSR requests.
   - Use INT 28h for narrowly defined deferred DOS-idle work.
   - Treat keyboard/timer-triggered SideKick-style popups as advanced work.
4. Separate transient and resident responsibilities.
   - Let the transient installer parse arguments, detect prior installation,
     release its environment block when appropriate, hook vectors, and call
     `keep` or `_dos_keep`.
   - Keep resident handlers, state, stack, signatures, and saved vectors in the
     retained region. Never retain pointers into discarded transient storage.
5. Keep every hardware ISR minimal.
   - Preserve registers and flags through Borland's `interrupt` ABI.
   - Record a request in a byte-sized `volatile` flag and chain or acknowledge
     the interrupt exactly once.
   - Do not allocate memory, use stdio, touch files, invoke the C++ runtime, or
     call DOS from a hardware ISR.
6. Defer substantial work until its prerequisites are proven safe.
   - Check reentrancy, critical-error state, nesting, video mode, and resident
     stack capacity before entering a popup.
   - Save and restore every screen, cursor, keyboard, timer, and application
     state element the popup changes.
7. Make installation and removal deterministic.
   - Publish a signature, version, and status function through a multiplex or
     private software interrupt.
   - On uninstall, refuse unless every hooked vector still points to this TSR.
     Restore vectors in reverse order and free memory only from a transient
     process after the resident code is unreachable.
8. Test incrementally in DOSBox-X.
   - First test install/detect/uninstall with no popup.
   - Then test interrupt chaining and request flags.
   - Add the smallest popup last, followed by repeated activation, multiple
     video modes, other TSR load orders, and failure-path tests.

## Output expectations

- Explain whether the design is a true TSR, a normal foreground application,
  or a task-switching system.
- State the hooked interrupts, chain order, DOS-call policy, resident-memory
  boundary, detection protocol, and uninstall refusal conditions.
- Provide a build command or `BUILD.BAT` only after discovering the compiler.
- Add Michael P. Burgus and `https://github.com/NeuralDrifter` to original code
  blocks produced for this project.
- Never claim a TSR is safe merely because it compiles or works once.
