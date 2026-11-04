OUTPUT_FORMAT ("elf32-littlearm", "elf32-bigarm", "elf32-littlearm")

/* Firmware entry point */
ENTRY(app_main)

MEMORY
{
	rom  (rx)  : ORIGIN = 0x00000000, LENGTH = 196608
	ram  (rwx) : ORIGIN = 0x20018050, LENGTH = 32688
}

__rom_start__	= ORIGIN(rom);
__rom_size__	= LENGTH(rom);
__ram_start__	= ORIGIN(ram);
__ram_size__	= LENGTH(ram);
__ram_end__	    = __ram_start__ + __ram_size__;
_sstart	    	= __ram_end__;		/* Top of RAM */

SECTIONS
{
	.text : 
	{
		KEEP(*(.app)) 					/* PLC APP 				*/
		
		. = ALIGN(4);
		_abi_start = .;
		KEEP(*(.app_abi_sec)) 			/* PLC APP ABI 			*/
		_abi_end = .;
		
		*(.text*)				    	/* Program code 		*/
		KEEP(*(.rodata*))				/* Read only data 		*/

		. = ALIGN(4);
		_pa_start = .;
		KEEP(*(.preinit_array))	    	/* Preinitarray 		*/
		_pa_end = .;

		. = ALIGN(4);
		_ia_start = .;
		KEEP (*(SORT(.init_array.*)))
		KEEP(*(.ctors))			    	/* Construcrs			*/
		_ia_end = .;

		. = ALIGN(4);
		_fia_start = .;
		KEEP(*(.fini_array))	        /* Destructors 			*/
		KEEP (*(SORT(.fini_array.*)))
		_fia_end = .;
	} >rom

	.data : ALIGN(4) 
	{
		_data_start = .;	    		/* Used in PLC startup 	*/
		*(.data*)				    	/* Initialized data 	*/
		_data_end = .;	    			/* Used in PLC startup 	*/
	} >ram AT > rom

	_data_loadaddr = LOADADDR(.data);

	.bss (NOLOAD) : ALIGN(4) 
	{
		*(.bss*)				    	/* Uninitialized data 	*/
		*(COMMON)				    	/* Common data 			*/
		_bss_end = .;					/* Used in PLC startup 	*/
	} >ram

	/* C++ exception unwinding stuff--needed by some toolchains */

	.ARM.extab : { *(.ARM.extab* .gnu.linkonce.armextab.*) } >rom

	__exidx_start = .;
	.ARM.exidx : { *(.ARM.exidx* .gnu.linkonce.armexidx.*) } >rom
	__exidx_end = .;
}
