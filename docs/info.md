<!---

This file is used to generate your project datasheet. Please fill in the information below and delete any unused
sections.

You can also include images in this folder and reference them in the markdown. Each image must be less than
512 kb in size, and the combined size of all images must be less than 1 MB.
-->

## How it works

OmniCore-1 is a 4-bit parallel In-Memory Computing (IMC) array built on SkyWater 130nm technology. It features 4 IMC cells that can store values like standard RAM flip-flops, but also execute parallel, in-place bitwise AND operations directly inside the memory array when the mode pin (ui[0]) is pulled high. This design eliminates the traditional Von Neumann memory transfer bottleneck.

## How to test

1. Activate the active-low reset (rst_n=0) for several clock cycles, then deactivate it (rst_n=1).
2. To write data to the memory register, set the mode pin (ui[0]=0) and apply a 4-bit value to the input pins (ui[4:1]). Toggle the clock (clk) to store the data. The stored value will be visible on the output pins (uo[3:0]).
3. To execute the In-Memory AND operation, set the mode pin (ui[0]=1) and apply the second 4-bit operand on the input pins (ui[4:1]). Toggle the clock (clk). The IMC register will compute the bitwise AND of the stored value and the input operand, updating the stored value in-place. The result will be visible on uo[3:0].

## External hardware

None. Can be tested using standard digital inputs and outputs.
