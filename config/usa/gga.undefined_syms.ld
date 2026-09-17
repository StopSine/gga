/* Absolute definitions for cross-section reference targets.
 *
 * Overlays branch into the fixed-window files and file 5 reaches into
 * overlay space. splat emits such targets as local .L / D_ labels which are
 * not exported, so the link fails.
 *
 * Declaring them in symbol_addrs instead would work for the link, but a
 * mid-function branch target declared type:func splits the containing
 * function, and N64Recomp then rejects the branch that crosses the new
 * boundary ("Unhandled branch") -- costing ten stubs. Defining the value
 * here satisfies the linker without creating a symbol splat has to place.
 */
.L08000074_64C864 = 0x64C864;
.L08000084_64C874 = 0x64C874;
.L08000984_64D174 = 0x64D174;
.L08000BA8_64D398 = 0x64D398;
.L8017C42C_5DEE8C = 0x5DEE8C;
.L8017C8A4_5DF304 = 0x5DF304;
.L8017D364_5DFDC4 = 0x5DFDC4;
.L8017DEB4_5E0914 = 0x5E0914;
.L80193CCC_5F672C = 0x5F672C;
.L80199E9C_5FC8FC = 0x5FC8FC;
.L8019ADC0_5FD820 = 0x5FD820;
.L8019ADC8_5FD828 = 0x5FD828;
.L8019AE14_5FD874 = 0x5FD874;
.L8019AE1C_5FD87C = 0x5FD87C;
.L8019AE40_5FD8A0 = 0x5FD8A0;
.L8019B4D8_5FDF38 = 0x5FDF38;
