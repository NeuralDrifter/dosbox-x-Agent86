# Borland DOS TSR engineering reference

## Contents

1. Execution model
2. Architecture choices
3. Borland real-mode ABI
4. Interrupt handlers and chaining
5. DOS reentrancy and deferred work
6. SideKick-style popup design
7. Resident memory ownership
8. Detection and uninstall
9. Implementation skeletons
10. Verification matrix
11. Sources

## 1. Execution model

A TSR is not a second process running in parallel. Its transient installer
returns control to DOS while a protected memory region and one or more
interrupt handlers remain. A later interrupt temporarily transfers the single
guest CPU execution stream into the resident code. The interrupted foreground
program resumes only after the TSR returns.

Use a TSR only when interrupt-driven residency is the desired behavior. Use a
task switcher, multitasking operating environment, or ordinary foreground
program when independent applications must make progress concurrently.

## 2. Architecture choices

Choose the smallest mechanism that meets the requirement:

| Requirement | Preferred mechanism | Risk |
|---|---|---|
| Service called by a cooperating program | Private software interrupt | Lowest |
| Work while DOS waits for console input | INT 28h idle hook | Moderate |
| Periodic flag or counter | BIOS timer tick INT 1Ch | Moderate |
| Global hotkey notification | Keyboard hook that only records a request | High |
| Full popup over arbitrary applications | Keyboard request plus carefully gated dispatcher | Very high |

Do not start with INT 09h if a software interrupt or INT 28h satisfies the
requirement. Hardware keyboard handlers must understand scan-code make/break
events, extended prefixes, keyboard-controller acknowledgement, PIC EOI, BIOS
buffer behavior, and the existing handler chain.

## 3. Borland real-mode ABI

Compile for a real-mode DOS target. Confirm the chosen memory model and inspect
the linker map. Do not assume code, data, heap, and stack ordering across tiny,
small, medium, compact, large, and huge models.

Include `<dos.h>` and use Borland's interrupt-vector types:

```c
/* Copyright (c) 2026 Michael P. Burgus - https://github.com/NeuralDrifter */
typedef void interrupt far (*interrupt_handler)(void);

static interrupt_handler previous_handler;

previous_handler = getvect(interrupt_number);
setvect(interrupt_number, replacement_handler);
```

Declare a C or C++ ISR with `interrupt far`. In C++, use a non-member function
or a static member function. The compiler-generated interrupt prologue and
epilogue preserve the register set expected by Borland and return with IRET.
Do not cast an ordinary function into an interrupt vector.

Install or restore a vector while interrupts are disabled, and keep that
critical section to the vector update itself. At normal installer level,
`disable()` followed by `enable()` is acceptable after confirming interrupts
were initially enabled. Inside reusable low-level code, preserve the previous
FLAGS interrupt state rather than enabling interrupts unconditionally.

Borland `keep(status, paragraphs)` and `_dos_keep(status, paragraphs)` invoke
DOS INT 21h function 31h. The paragraph count is the retained process size in
16-byte units. They do not infer the correct boundary for the design.

## 4. Interrupt handlers and chaining

An ISR must have one ownership strategy:

- **Chain:** perform minimal work and invoke or transfer to the previous
  handler using the compiler-supported interrupt function type.
- **Replace:** fully perform the hardware protocol, including controller and
  PIC acknowledgement, and do not call the previous handler.

Never acknowledge the same hardware interrupt twice. If the previous IRQ
handler performs the keyboard-controller acknowledgement or PIC EOI, the new
handler must not repeat it. Preserve chain order and assume later TSRs may hook
the same vector.

Use byte-sized `volatile` fields for ISR-to-dispatcher flags on 8086-class
targets. `volatile` prevents compiler caching; it does not make compound
operations atomic. Protect multi-byte shared state or use a stable-read
protocol.

Keep a hardware ISR bounded:

- no `printf`, streams, files, heap allocation, environment access, or `exit`;
- no non-reentrant library calls;
- no long loops or waits;
- no floating-point operations;
- no foreground program stack assumptions;
- no recursive activation.

A production popup should enter through a small assembly wrapper that switches
to a dedicated resident stack before calling substantial C code. A tiny ISR
that only sets a flag may use the interrupted stack if its bounded worst-case
usage has been reviewed, but this is not sufficient for a popup UI.

## 5. DOS reentrancy and deferred work

DOS is generally non-reentrant. A hardware interrupt can arrive while DOS is
already servicing INT 21h; calling DOS again can corrupt internal DOS stacks or
state.

Apply these rules:

1. Never call DOS from INT 09h, INT 08h, or INT 1Ch.
2. Obtain and retain the InDOS pointer during installation if deferred code
   needs to test DOS activity.
3. Account for the critical-error state separately; InDOS alone is not a
   universal safety proof across DOS versions.
4. Use INT 28h only for operations documented as safe during DOS idle, and
   respect the DOS-version restrictions on which INT 21h functions are legal.
5. Prefer direct video memory and preloaded resident data for a popup, but
   still guard against incompatible video modes and nested activation.
6. Treat BIOS and third-party resident services as potentially non-reentrant
   unless their contracts explicitly say otherwise.

If safety cannot be proven at the requested interruption point, leave a
pending flag set and wait. Delayed activation is better than corrupting the
foreground program.

## 6. SideKick-style popup design

SideKick created the appearance of multitasking by suspending the foreground
application, presenting resident tools, and restoring the application state.
It did not allow both applications to execute simultaneously.

A robust popup requires all of the following:

- hotkey recognition without accidentally consuming unrelated keystrokes;
- a reentrancy guard and pending-request state machine;
- a dedicated resident stack;
- confirmation that DOS and critical-error handling are safe;
- supported video-mode detection;
- save/restore of the exact affected video page, screen region, cursor shape,
  cursor position, and relevant adapter state;
- resident-only code and data during activation;
- no disk or configuration-file dependency while interrupted;
- restoration on every exit path, including cancellation and errors;
- a clear policy for timer, sound, mouse, and keyboard events while the
  foreground program is paused.

Text-mode popups are substantially safer than arbitrary graphics overlays.
For a graphics game, do not assume that saving 80x25 text memory preserves the
display. Identify the adapter and mode, save the correct framebuffer or refuse
to pop up. Pausing a timing-sensitive game can also disturb sound and input
even if the screen is restored correctly.

## 7. Resident memory ownership

DOS function 31h keeps a count of paragraphs beginning at the process PSP. A
wrong count causes one of two failures:

- too small: later programs overwrite resident code, data, or stack;
- too large: conventional memory is leaked unnecessarily.

Do not paste a generic `_SS`, `_SP`, or `_psp` formula without proving the
linker's segment order for the selected memory model. Instead:

1. Produce and inspect the linker `.MAP` file.
2. Identify the highest address required by resident code, resident data, and
   the dedicated resident stack.
3. Measure from the PSP segment to the first byte after that region.
4. Round upward to a 16-byte paragraph.
5. Include the PSP and any compiler/runtime structures used after residency.
6. Verify the retained block with a DOS memory-map utility after installation.

The environment block is a separate DOS allocation referenced by the PSP. A
transient installer may release it before staying resident if no resident code
uses environment strings. Validate the segment first and use DOS memory-free
services from normal process context, never from an ISR.

Close files and finish configuration before residency. Do not retain pointers
to command-line buffers, environment strings, transient heap objects, overlay
segments, or library state that will be released or restored.

## 8. Detection and uninstall

Provide an installation protocol rather than scanning memory heuristically.
A private software interrupt or multiplex protocol should return:

- a stable signature unlikely to collide;
- TSR version and compatibility information;
- installed, busy, and popup-active states;
- the resident PSP or a controlled uninstall request when needed.

On a second invocation, detect the existing TSR before installing another
copy. For removal:

1. Require normal DOS process context and an inactive resident service.
2. Disable new activation.
3. Verify each hooked vector still equals this TSR's current handler.
4. If any vector points elsewhere, refuse removal because another TSR is above
   this one in the chain.
5. Restore owned vectors in reverse installation order.
6. Confirm no resident handler remains reachable.
7. Free the resident environment block if it was retained.
8. Free the resident PSP memory block from the transient uninstaller.

Never free the memory block from code executing inside that block. Never
restore a saved vector over a newer TSR's hook.

## 9. Implementation skeletons

This skeleton illustrates separation of ISR notification from deferred work.
It is not a complete keyboard or popup implementation:

```c
/* Copyright (c) 2026 Michael P. Burgus - https://github.com/NeuralDrifter */
#include <dos.h>

typedef void interrupt far (*interrupt_handler)(void);

static interrupt_handler previous_tick;
static volatile unsigned char service_requested;
static volatile unsigned char service_active;

static void interrupt far tick_handler(void)
{
    if (!service_active && should_request_service())
        service_requested = 1;

    previous_tick();
}

static void dispatch_if_safe(void)
{
    if (!service_requested || service_active || !dos_state_is_safe())
        return;

    service_active = 1;
    service_requested = 0;
    run_on_dedicated_resident_stack();
    service_active = 0;
}
```

The omitted functions are design-specific. Do not implement
`should_request_service()` by doing slow work in the ISR, and do not implement
`dos_state_is_safe()` as an InDOS-only guess.

The installer sequence should remain ordinary process code:

```c
/* Copyright (c) 2026 Michael P. Burgus - https://github.com/NeuralDrifter */
static void install_resident_service(void)
{
    unsigned resident_paragraphs;

    refuse_if_already_installed();
    finish_configuration_and_close_files();
    release_unused_environment_block();
    resident_paragraphs = calculate_from_verified_map_boundary();

    previous_tick = getvect(0x1c);
    disable();
    setvect(0x1c, tick_handler);
    enable();

    keep(0, resident_paragraphs);
}
```

Keep the placeholder names until their contracts are implemented and tested.
A guessed memory formula or stubbed safety check is not a finished TSR.

## 10. Verification matrix

Test from a recoverable DOSBox-X snapshot and retain the compiler map file.

| Area | Required checks |
|---|---|
| Installation | first install, duplicate refusal, signature/version query |
| Memory | before/after free memory, retained paragraph boundary, environment release |
| Interrupts | previous handler still runs, no lost ticks/keys, no double EOI |
| Reentrancy | activation during DOS activity is deferred, nested request refused |
| Stack | worst-case popup path, repeated activation, guard bytes if practical |
| Display | supported text modes, unsupported graphics refusal, exact restoration |
| Compatibility | shell, editor/compiler, game, other TSR loaded before and after |
| Removal | normal unload, busy refusal, non-top-of-chain refusal, reinstall |
| Failure | timeout, unsupported DOS version, unknown video mode, missing vector |

Compile with warnings enabled where the Borland version permits. A successful
build proves syntax and linkage only. Exercise hundreds of interrupt and popup
cycles before considering the design stable.

## 11. Sources

- Borland C++ 4.0 DOS Reference: `keep`, `_dos_keep`, `getvect`, and `setvect`.
  https://bitsavers.org/pdf/borland/borland_C%2B%2B/Borland_C%2B%2B_Version_4.0_DOS_Reference_Oct93.pdf
- Borland C++ 4.0 Library Reference: interrupt-vector types and compiler ABI.
  https://bitsavers.org/pdf/borland/borland_C%2B%2B/Borland_C%2B%2B_Version_4.0_Library_Reference_Sep93.pdf
- Borland Turbo Debugger 4.5 User's Guide: transient/resident TSR debugging.
  https://bitsavers.org/pdf/borland/turbo_debugger/Turbo_Debugger_4.5_Users_Guide_1994.pdf
- Borland SideKick 1.5 Owner's Handbook: resident operation and TSR load order.
  https://bitsavers.org/pdf/borland/sidekick/Sidekick_Version_1.5_Owners_Manual_Mar85.pdf
- Ralf Brown's Interrupt List: DOS INT 21h function 31h reference.
  https://fd.lod.bz/rbil/interrup/dos_kernel/2131.html
