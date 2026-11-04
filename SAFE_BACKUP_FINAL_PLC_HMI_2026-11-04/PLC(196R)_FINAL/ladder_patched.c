#define IMG_REVISION 531
#include "alwaysinc.c"




/*
*********************************************************************************************************
*                                          FUNCTION PROTOTYPES
*********************************************************************************************************
*/


//-------------------------------------------------------------------------------------------------------
// 									      APPLICATION FUNCTIONS
//-------------------------------------------------------------------------------------------------------
#ifdef PLC_SIM
extern void app_main(U32 app_addr);
#else
extern void app_main(U32 app_addr) __attribute__((section(".app")));
#endif //PLC_SIM

int app_init(void);
int app_exit(void);
int app_proc(void);

#if IMG_REVISION >= 527	
int dummyvarformodules;
#endif


//-------------------------------------------------------------------------------------------------------
// 									 			 EVENTS
//-------------------------------------------------------------------------------------------------------
void 	event_din_onchanged		(void);
void 	event_hso_onfinished	(U32 chan, U32 count);
void 	event_enc_onfinished	(U32 chan, U32 count);

//-------------------------------------------------------------------------------------------------------
// 									 		HELPER FUNCTIONS
//-------------------------------------------------------------------------------------------------------
void 	get_module_info			(U32 *addr, U32 *size);
void 	get_devtag_info			(U32 *dev_addr, U32 *dev_size, U32 *tag_addr, U32 *tag_size);


/*
*********************************************************************************************************
*                                           LOCAL DEFINITIONS
*********************************************************************************************************
*/

static U32 dummy_data;

// PLC variable sizes
#define PLC_MAXQP		(280)
#define PLC_MAXIP		(280)
#define PLC_MAXSB		(128)
#define PLC_MAXSI		(256)

// System address definitions
#define APPIF_ADDR		(0x20018000)	// Points appif_t structure. Size = 16
#define DRVIF_ADDR		(0x20018010)	// Points drvif_t structure. Size = 24
#define LIBIF_ADDR		(0x20018030)	// Points libif_t structure. Size = 20
#define PLCRAM_ADDR		(0x20018050)	// Points PLC user RAM. 	 Size = 32688
#define PLCRAM_SIZE		(0x20020000-PLCRAM_ADDR)

#define PLCHDR_SIZE 	(0x00000010)
#define PLCAPP_VER		(0x0001)

// PLC variables address retrieve macro
#define QP_Addr(x)		((U32)(&(plcvar.QP[x])))
#define IP_Addr(x)		((U32)(&(plcvar.IP[x])))
#define IPFil_Addr(x)	((U32)(&IP_filt[x]))
#define SI_Addr(x)		((U32)(&SI[x]))
#define SB_Addr(x)		((U32)(&SB[x]))
#define CVal(x)			((U32)(x))
#define DMY_Addr()		((U32)(&dummy_data))
#define IPADDR(a,b,c,d)	((d<<24UL)|(c<<16UL)|(b<<8UL)|(a))

// Modbus master process definitions
#define MBPROC_MAX_DEVCNT		(10)
#define MBPROC_MAX_TAGCNT		(256)
#define MBPROC_TYP_READ			(0)
#define MBPROC_TYP_WRITE		(1)
#define MBPROC_STAT_STOP		(0)
#define MBPROC_STAT_ONETIME		(1)
#define MBPROC_STAT_CONTINOUS	(2)

#define MB_COIL_STAT_START		(1)
#define MB_COIL_STAT_END		(9999)
#define MB_INPUT_STAT_START		(10001)
#define MB_INPUT_STAT_END		(19999)
#define MB_INPUT_REG_START		(30001)
#define MB_INPUT_REG_END		(39999)
#define MB_HOLDING_REG_START	(40001)
#define MB_HOLDING_REG_END		(49999)

/*
*********************************************************************************************************
*                                         DRIVER DEDICATED DEFINITIONS
*********************************************************************************************************
*/

// driver specific definitions
#define DIN_CHAN_SIZE	(9)
#define DOUT_CHAN_SIZE	(6)
#define AIN_CHAN_SIZE	(1)
#define AOUT_CHAN_SIZE	(1)
#define HSO_CHAN_SIZE	(3)
#define ENC_CHAN_SIZE	(3)

enum
{
    REC_TRIGER,
    REC_PERIODIC,
};

// format indexes
enum
{
    FRMT_BIT,

    FRMT_INT8,
    FRMT_INT16,
    FRMT_INT32,

    FRMT_UINT8,
    FRMT_UINT16,
    FRMT_UINT32,

    FRMT_FLOAT,
}; 


// Driver ID's
enum
{
   DRIVER_INVALID = -1,
    DRIVER_DIN,
    DRIVER_DOUT,
    DRIVER_AIN,
    DRIVER_AOUT,
    DRIVER_SEN,
    DRIVER_LDC,
    DRIVER_ENC,
    DRIVER_HSO,
    DRIVER_EXP,
    DRIVER_RTC,
    DRIVER_COM,
    DRIVER_WMI,
    DRIVER_PID,
    DRIVER_LOG,
	DRIVER_NET,
	#if IMG_REVISION >= 516
	DRIVER_NVM,
	#endif	
	#if IMG_REVISION >= 523
	DRIVER_MAT,
	#endif			
    DRIVER_MAX, 

};

// Analog input types
enum
{
	AIN_TYPE_INVALID,

	AIN_TYPE_Volt,
	AIN_TYPE_mA_0_20,
	AIN_TYPE_mA_4_20,
};

// Analog output types
enum
{
	AOUT_TYPE_INVALID,

	AOUT_TYPE_Volt,
	AOUT_TYPE_mA_0_20,
	AOUT_TYPE_mA_4_20,
};

// Sensor input types
enum
{
	SEN_TYPE_INVALID,

	SEN_TYPE_PT100,
	SEN_TYPE_PT1000,
	SEN_TYPE_TC_B,
	SEN_TYPE_TC_E,
	SEN_TYPE_TC_J,
	SEN_TYPE_TC_K,
	SEN_TYPE_TC_N,
	SEN_TYPE_TC_R,
	SEN_TYPE_TC_S,
	SEN_TYPE_TC_T,
};

// Loadcell input types
enum
{
	LDC_TYPE_INVALID,

	LDC_TYPE_2mV,
	LDC_TYPE_4mV,
};

// Driver ioctl request codes
enum
{
	IOCTL_DIN_INIT,
    IOCTL_DIN_GETINPUTPTR,
    IOCTL_DIN_GETFILTERPTR,

    IOCTL_DOUT_INIT,

    IOCTL_AIN_INIT,
    IOCTL_AIN_SCALE_SET,
    IOCTL_AIN_UPDATE,

    IOCTL_AOUT_INIT,
    IOCTL_AOUT_SCALE_SET,
    IOCTL_AOUT_UPDATE,

    IOCTL_SEN_INIT,
    IOCTL_SEN_SCALE_SET,
    IOCTL_SEN_UPDATE,

    IOCTL_LDC_INIT,
    IOCTL_LDC_SCALE_SET,
    IOCTL_LDC_UPDATE,

    IOCTL_ENC_INIT,
    IOCTL_ENC_START,
    IOCTL_ENC_STOP,
    IOCTL_ENC_CLEAR,

    IOCTL_HSO_INIT,
    IOCTL_HSO_DEINIT,
    IOCTL_HSO_START,
    IOCTL_HSOC_START,
    IOCTL_HSO_STOP,
    IOCTL_HSO_SETVALUE,

    IOCTL_EXP_INIT,
    IOCTL_EXP_START,
    IOCTL_EXP_STOP,
    IOCTL_EXP_UPDATEPARAMS,

    IOCTL_RTC_INIT,
    IOCTL_RTC_SETTIME,
    IOCTL_RTC_SETDATE,
    IOCTL_RTC_SETDATETIME,

    IOCTL_COM_MBSLAVEINIT,
    IOCTL_COM_MBMASTERINIT,
    IOCTL_COM_MBMASTERREAD,
    IOCTL_COM_MBMASTERWRITE,
    IOCTL_COM_ASCIICONFIG,
    IOCTL_COM_ASCIIWRITE,

    IOCTL_WMI_INIT,
    IOCTL_WMI_POSTMAIL,

    IOCTL_PID_INIT,
    IOCTL_PID_SETPARAMS,
    IOCTL_PID_GETPARAMS,
    IOCTL_PID_ATUNE_START,
    IOCTL_PID_ATUNE_STOP,

    IOCTL_COM_ASCIIPARSE,

	IOCTL_LOG_INIT,
    IOCTL_LOG_START,
    IOCTL_LOG_STOP,
    IOCTL_LOG_ADDITEM,
    IOCTL_LOG_TRIG,
    IOCTL_LOG_GETFILENAME,
    IOCTL_LOG_CLOSE,
    IOCTL_LOG_ENABLE,
    IOCTL_LOG_DISABLE, 
	
    IOCTL_NET_SETCONFIG,
    IOCTL_NET_GETCONFIG, 
	
	#if IMG_REVISION >= 516
    IOCTL_NVM_SAVE,
    IOCTL_NVM_LOAD,
    IOCTL_WMI_POSTALR,
    IOCTL_HSO_DUTY ,
    IOCTL_COM_POSTASCII,
	#endif

	
	#if IMG_REVISION >= 521
    IOCTL_HSOC_START2,	
	#endif

	#if IMG_REVISION >= 522
    IOCTL_HSOC_PAUSE, 
    IOCTL_HSOC_STARTPWM,
	#endif
	
	#if IMG_REVISION >= 524
	IOCTL_HSO_SETVALUE2,
	IOCTL_HSO_UPDATE,
	#endif
	
	#if IMG_REVISION >= 525
	IOCTL_COM_MAILINIT,
	IOCTL_COM_MAILSEND,
	#endif
	
	#if IMG_REVISION >= 526
	IOCTL_COM_ASCIIBUFFER,	
	#endif
	
};

      
		
		
// Driver signal codes
enum
{
	SIGNAL_DIN_ONCHANGE,
	SIGNAL_HSO_ONFINISH,
	SIGNAL_ENC_ONFINISH,
};

// encoder input types
enum
{
	ENC_IN_A = 0x0001,
	ENC_IN_B = 0x0002,
	ENC_IN_Z = 0x0004,

	ENC_DIR_AB = 0x0010,
	ENC_DIR_BA = 0x0020,
};

// sensor types
typedef enum
{
	SEN_INVALID,	// 0

	SEN_PT100,		// 1
	SEN_PT1000,		// 2
	SEN_TC_B,		// 3
	SEN_TC_E,		// 4
	SEN_TC_J,		// 5
	SEN_TC_K,		// 6
	SEN_TC_N,		// 7
	SEN_TC_R,		// 8
	SEN_TC_S,		// 9
	SEN_TC_T,		// 10
	SEN_NTC,		// 11
	SEN_mV,			// 12
    SEN_OHM,        // 13 
	SEN_MAX,
} sentype_t;

// PID controller type
enum
{
	CONTROL_NONE,
	CONTROL_OPTIMUM,
	CONTROL_TIGHT,
	CONTROL_SMOOTH,
};

// RTC months
enum
{
	RTC_January = 1,
	RTC_February,
	RTC_March,
	RTC_April,
	RTC_May,
	RTC_June,
	RTC_July,
	RTC_August,
	RTC_September,
	RTC_October,
	RTC_November,
	RTC_December,
};

// RTC day of week
enum
{
	RTC_Monday = 1,
	RTC_Tuesday,
	RTC_Wednesday,
	RTC_Thursday,
	RTC_Friday,
	RTC_Saturday,
	RTC_Sunday,
};

// Communication media types
enum
{
	COM_MED_RS232,
	COM_MED_RS485,
	COM_MED_TCPSLAVE,
	COM_MED_TCPMASTER,
	COM_MED_MAX,
};

enum
{
    MB_DATA_LE,
    MB_DATA_BE,
}; 

/*
*********************************************************************************************************
*                                         LIBRARY DEDICATED DEFINITIONS
*********************************************************************************************************
*/

// Library ID's
enum
{
	LIBRARY_INVALID = -1,
	LIBRARY_MATH,
	LIBRARY_MEM,
	LIBRARY_MAX,
};

// Library ioctl request codes
enum
{
    IOCTL_DUMMY_0,
    IOCTL_DUMMY_1,

    IOCTL_MEM_INIT,
    IOCTL_MEM_SETVARBIT,
    IOCTL_MEM_SETVARWORD,
    IOCTL_MEM_SETVARINT,
    IOCTL_MEM_SETVARFLOAT,
    IOCTL_MEM_SETVARINPUT,
	
	#if IMG_REVISION >= 515
	IOCTL_MEM_SETVARINFO, 
	#endif

    IOCTL_MATH_INIT,
    IOCTL_MATH_CALCSUN,
    IOCTL_MATH_CALCPRAYER,
    IOCTL_MATH_MULDOUBLE,
    IOCTL_MATH_DIVDOUBLE,
	
	#if IMG_REVISION >= 523
	IOCTL_MATH_ARCSIN,
	IOCTL_MATH_ARCCOS,
	IOCTL_MATH_ARCTAN
	#endif
};


/*
*********************************************************************************************************
*                                       EXPANSION DEDICATED DEFINITIONS
*********************************************************************************************************
*/

// expansion module types
#define EXM_TYPE_INVALID	( 0)
#define EXM_TYPE_EXM88R		( 1)
#define EXM_TYPE_EXM88T		( 3)
#define EXM_TYPE_EXM42A		( 5)
#define EXM_TYPE_EXM02A		( 6)
#define EXM_TYPE_EXM40A		( 7)
#define EXM_TYPE_EXM40T		( 9)
#define EXM_TYPE_EXM20L		(10)
#define EXM_TYPE_EXM40P		(11)
#define EXM_TYPE_EXM10L		(12)
#define EXM_TYPE_EXM40U		(14)
#define EXM_TYPE_EXM16T		(15)
#define EXM_TYPE_EXM16I		(16)
#define EXM_TYPE_EXM20U     (17)
#define GXM_TYPE_40I        (18)
#define GXM_TYPE_80I        (19)
#define GXM_TYPE_04T        (20)
#define GXM_TYPE_08T        (21)
#define GXM_TYPE_04R        (22)
#define GXM_TYPE_08R        (23)
#define GXM_TYPE_12R        (24)
#define GXM_TYPE_44R        (25) 
#define GXM_TYPE_06A        (27) 
#define GXM_TYPE_04ANX      (28) 
#define GXM_TYPE_60P        (29) 
#define GXM_TYPE_20LF       (30)
#define GXM_TYPE_10LF       (31)

#if IMG_REVISION == 526
#define GXM_TYPE_40UAN      (32)
#endif


#if IMG_REVISION == 527	
#define GXM_TYPE_20UT       (32) // Universal Temperature 2 Channel
#define GXM_TYPE_40UT       (33) // Universal Temperature 4 Channel
#endif

#if IMG_REVISION >= 528
#define GXM_TYPE_40UAN      (32)
#define GXM_TYPE_20UT       (33) // Universal Temperature 2 Channel
#define GXM_TYPE_40UT       (34) // Universal Temperature 4 Channel
#endif

#if IMG_REVISION >= 529
#define GXM_TYPE_20PT       (35)
#define GXM_TYPE_40PT       (36)
#define GXM_TYPE_20TC       (37)
#define GXM_TYPE_40TC       (38)
#endif

#if IMG_REVISION >= 530
#define GXM_TYPE_20LX       (39)
#define GXM_TYPE_10LX       (40)
#endif

/*
*********************************************************************************************************
*                                             LOCAL TYPES
*********************************************************************************************************
*/

// application function type
typedef int (*app_func_t)(void);

// entry function type
typedef void (*entry_fp_t)(U32);

// load function type
typedef void (*load_fp_t)(void);

// PLC interface type
typedef struct __attribute__ ((packed, aligned(1)))
{
   U8  *QP;
    U8  *QP_force;
    U8  *IP;
    U8  *IP_force;
    U8  *IP_prev;
    U8  *IP_filt;
    I32 *SI;
    U8  *SB;
    U32  RAMAddr;
    U32  MemAddr;
    U32  MemLen;
	U32  ABIStart;
    U32  InitAddr;
	U32  PowerOnAddr;
} plcif_t;

// application interface type
typedef struct
{
	app_func_t init;
	app_func_t exit;
	app_func_t proc;
	plcif_t   *plcif;
} appif_t;

// driver interface type
typedef struct 
{
	int (*open)(int, U32);
	int (*close)(int);
	int (*read)(int, void*, int);
	int (*write)(int, void*, int);
	int (*ioctl)(int, U32, void*);
	int (*connect)(int, U32, void*);
} drvif_t;

// library interface type
typedef struct
{
	int (*open)(int, U32);
	int (*close)(int);
	int (*read)(int, void*, int);
	int (*write)(int, void*, int);
	int (*ioctl)(int, U32, void*);
	int (*snprintf)(char*, U32, const char*,  ... );
} libif_t;

// Modbus device data type
typedef struct __attribute__ ((packed, aligned(1)))
{
    U32 media;

    struct
    {
        U8  proto;
        U8  parity;
        U8  databits;
        U8  stopbits;
        U32 baudrate;
    } ser;
    struct
    {
        U32 ipaddr;
        U32 port;
    } tcp;

    U16 timeout;
#if IMG_REVISION <= 513
    U16 retry;
#else
    U8  retry;
    U8  endian;
#endif
    U32 stat_addr;
} mbdev_t;


// Modbus tag data type
typedef struct
{
	U8  dev;
	U8  netid;
	U16 type;
	U32 remote_addr;
	U32 local_addr;
	U32 len;
	U32 stat_addr;

	#if IMG_REVISION >= 517	
	U32 enab_addr;
	#endif
	
	#if IMG_REVISION >= 518
	U32 endian;
	#endif
	
	#if IMG_REVISION >= 519
	U32 addr_type; 
	#endif
	
	
} mbtag_t;

// Application interface structure
typedef struct
{
    // Entry point
    entry_fp_t 	  entry;

    // Startup interface
    U32 		* sstart;
    U32 		* data_loadaddr;
    U32 		* data_start;
    U32 		* data_end;
    U32 		* bss_end;
    load_fp_t 	* pa_start;
    load_fp_t 	* pa_end;
    load_fp_t 	* ia_start;
    load_fp_t 	* ia_end;
    load_fp_t 	* fia_start;
    load_fp_t 	* fia_end;
} app_abi_t;


/*
*********************************************************************************************************
*                                     	PLC VARIABLES ACCESS MACROS
*********************************************************************************************************
*/

#define PLC_GET_1ms()		(SB[5]&1)
#define PLC_GET_10ms()		(SB[6]&1)
#define PLC_GET_100ms()		(SB[2]&1)
#define PLC_GET_500ms()		(SB[3]&1)
#define PLC_GET_1000ms()	(SB[4]&1)


/*
*********************************************************************************************************
*                                            by MMC
*********************************************************************************************************
*/
 #define GmtIntAdrOf (I32)&
typedef enum
{
    sunrise,
	sunset,
	imsak,
	gunes,
	ogle,
	ikindi,
	aksam,
	yatsi,
	acilar
};
 struct
    {
		I32 saat;
		I32 dakika;
		I32 saniye;
    } static  astrozaman[9];
	
static float mmcabs_float(float deger)
{
    if (deger<0)
        return (deger *-1);
    else
        return (deger);
}

static int mmcabs_int(int deger)
{
    if (deger<0)
        return (deger *-1);
    else
        return (deger);
}

typedef enum {MOTION_STOP,HYR,HYF,HNYR,HNYF,MOTION_STOP_ERR,HNYFdiv2,HYRdiv4,MOVNONE,MOTION_STOP_RMP}hareketmodu;
typedef enum {ZeroPass,onePass,twoPass}homemodu;

U32 mem_flash[1024];
U32 flash_dummy_degisken=0;

U32 addr_of_1byte_input[1024];
U32 addr_of_1byte[1024];
U32 addr_of_2byte[1024];
U32 addr_of_4byte[1024];
U32 dummydegisken;
U16 dummydegisken1;
U8 dummydegisken2;

void modb_array_init(void)
{
    int i;   
    for (i=0; i<1024; i++)
    {
        addr_of_1byte[i] =  (U32)&dummydegisken2;
        addr_of_2byte[i] = (U32)&dummydegisken1;
        addr_of_4byte[i] = (U32)&dummydegisken;
		addr_of_1byte_input[i]=(U32)&dummydegisken2;
    }//for
}

U8 cl_vrunonce;
U8 cl_vrunonce2;


	
/*
*********************************************************************************************************
*                                            LOCAL VARIABLES
*********************************************************************************************************
*/

// application entry point
static U32 app_entry_point;

// application interface
static appif_t *appif;

// driver interface
static drvif_t *drvif;

// library interface
static libif_t *libif;

// PLC interface
static plcif_t plcif;

#ifdef PLC_SIM

// application interface
static appif_t my_appif;

// driver interface
static drvif_t my_drvif;

// library interface
static libif_t my_libif;
#endif //PLC_SIM

// driver files descriptors
static int din;		// Digital inputs
static int dout;	// Digital outputs
static int ain;		// Analog inputs
static int aout;	// Analog outputs
static int sen;		// Sensor inputs
static int ldc;		// Load-cell inputs
static int hso;		// High speed outputs
static int enc;		// Encoder inputs
static int gxm;		// Expansion modules
static int rtc;		// RTC
static int com;		// Communication devices
static int wmi;		// WMI
static int pid;		// PID
static int net;		// PID


// library files descriptors
static int math;	// Mathematics library devices
static int memi;	// Memory interface
static int minfo;	// CPU info

// PLC application variables
static U8  IP_prev[PLC_MAXIP];
static U8  IP_filt[PLC_MAXIP];
static I32 SI	  [PLC_MAXSI];
static U8  SB	  [PLC_MAXSB];

#if IMG_REVISION == 528
static char mesaj[11];
#endif
#if IMG_REVISION >= 529
static char mesaj[2034];
#endif

typedef struct __attribute__((__packed__))
{
U8  IP	  [280];
U8  QP	  [280];
U8  IP_Force0	  [280];
U8  IP_Force1	  [280];
int ref_degisken;
int plc_lad_delay_sayac;
struct{
int CPU_HSC0_Type;
int CPU_HSC0_Cnt;
int CPU_HSC0_Dir;
int CPU_HSC0_Freq;
int CPU_HSC0_FreqPer;
int CPU_HSC1_Type;
int CPU_HSC1_Cnt;
int CPU_HSC1_Dir;
int CPU_HSC1_Freq;
int CPU_HSC1_FreqPer;
int CPU_HSC2_Type;
int CPU_HSC2_Cnt;
int CPU_HSC2_Dir;
int CPU_HSC2_Freq;
int CPU_HSC2_FreqPer;
int CPU_COM1_NetID;
int CPU_COM1_Timeout;
int CPU_COM1_ETX;
int CPU_COM1_Status;
int CPU_COM1_ErrVal;
int CPU_COM1_BufferByteAdet;
int CPU_COM2_NetID;
int CPU_COM2_Timeout;
int CPU_COM2_ETX;
int CPU_COM2_Status;
int CPU_COM2_ErrVal;
int CPU_COM2_BufferByteAdet;
int CPU_Eth_slave_timeout;
int CPU_SlvDev0_timeout;
int CPU_SlvDev1_timeout;
int CPU_SlvDev2_timeout;
int CPU_SlvDev3_timeout;
int CPU_SlvDev4_timeout;
int CPU_LadderFreq;
int CPU_WMIStatus;
int ps2_0;
int pe2_0;
int ps2_1;
int pe2_1;
int ps2_2;
int pe2_2;
int ps2_3;
int pe2_3;
int ps2_5;
int pe2_5;
int ps2_6;
int pe2_6;
int ps2_7;
int pe2_7;
int ps2_8;
int pe2_8;
int ps2_9;
int pe2_9;
int ps2_10;
int pe2_10;
int ps2_11;
int pe2_11;
int ps2_12;
int pe2_12;
int ps2_13;
int pe2_13;
int ps2_14;
int pe2_14;
int ps2_15;
int pe2_15;
int ps2_16;
int pe2_16;
int ps2_17;
int pe2_17;
int ps2_18;
int pe2_18;
int ps2_19;
int pe2_19;
int ps2_20;
int pe2_20;
int ps2_21;
int pe2_21;
int ps2_22;
int pe2_22;
int ps2_23;
int pe2_23;
int ps2_24;
int pe2_24;
int ps2_25;
int pe2_25;
int ps2_26;
int pe2_26;
int ps2_27;
int pe2_27;
int ps2_28;
int pe2_28;
int ps2_29;
int pe2_29;
int ps2_30;
int pe2_30;
int ps2_31;
int pe2_31;
int ps2_32;
int pe2_32;
int ps2_33;
int pe2_33;
int ps2_34;
int pe2_34;
int ps2_35;
int pe2_35;
int ps2_36;
int pe2_36;
int ps2_37;
int pe2_37;
int ps2_38;
int pe2_38;
int ps2_39;
int pe2_39;
int ps2_40;
int pe2_40;
int ps2_41;
int pe2_41;
int ps2_42;
int pe2_42;
int ps2_43;
int pe2_43;
int ps2_44;
int pe2_44;
int ps2_45;
int pe2_45;
int ps2_46;
int pe2_46;
int ps2_47;
int pe2_47;
int ps2_48;
int pe2_48;
int ps2_49;
int pe2_49;
int ps2_50;
int pe2_50;
int ps2_51;
int pe2_51;
int ps2_52;
int pe2_52;
int ps2_53;
int pe2_53;
int ps2_54;
int pe2_54;
int ps2_55;
int pe2_55;
int ps2_56;
int pe2_56;
int ps2_57;
int pe2_57;
int ps2_58;
int pe2_58;
int ps2_59;
int pe2_59;
int ps2_60;
int pe2_60;
int ps2_61;
int pe2_61;
int ps2_62;
int pe2_62;
int ps2_63;
int pe2_63;
int ps2_64;
int pe2_64;
int ps2_65;
int pe2_65;
int ps2_66;
int pe2_66;
int ps2_67;
int pe2_67;
int ps2_68;
int pe2_68;
int ps2_69;
int pe2_69;
int ps2_70;
int pe2_70;
int ps2_71;
int pe2_71;
int ps2_72;
int pe2_72;
int ps2_73;
int pe2_73;
int ps2_74;
int pe2_74;
int ps2_75;
int pe2_75;
int ps2_76;
int pe2_76;
int ps2_77;
int pe2_77;
int ps2_78;
int pe2_78;
int ps2_79;
int pe2_79;
int ps2_80;
int pe2_80;
int ps2_81;
int pe2_81;
int ps2_82;
int pe2_82;
int ps2_83;
int pe2_83;
int ps2_84;
int pe2_84;
int ps2_85;
int pe2_85;
int ps2_86;
int pe2_86;
int ps2_87;
int pe2_87;
int ps2_88;
int pe2_88;
int ps2_89;
int pe2_89;
int ps2_90;
int pe2_90;
int ps2_91;
int pe2_91;
int ps2_92;
int pe2_92;
int ps2_93;
int pe2_93;
int ps2_94;
int pe2_94;
int ps2_95;
int pe2_95;
int ps2_96;
int pe2_96;
int ps2_97;
int pe2_97;
int ps2_98;
int pe2_98;
int ps2_99;
int pe2_99;
int ps2_100;
int pe2_100;
int ps2_101;
int pe2_101;
int ps2_102;
int pe2_102;
int ps2_103;
int pe2_103;
int ps2_104;
int pe2_104;
int ps2_105;
int pe2_105;
int ps2_106;
int pe2_106;
int ps2_107;
int pe2_107;
int ps2_108;
int pe2_108;
int ps2_109;
int pe2_109;
int ps2_110;
int pe2_110;
int ps2_111;
int pe2_111;
int ps2_112;
int pe2_112;
int ps2_113;
int pe2_113;
int ps2_114;
int pe2_114;
int ps2_115;
int pe2_115;
int ps2_116;
int pe2_116;
int ps2_117;
int pe2_117;
int ps2_118;
int pe2_118;
int ps2_119;
int pe2_119;
int ps2_120;
int pe2_120;
int ps2_121;
int pe2_121;
int ps2_122;
int pe2_122;
int ps2_123;
int pe2_123;
int ps2_124;
int pe2_124;
int ps2_125;
int pe2_125;
int ps2_126;
int pe2_126;
int ps2_127;
int pe2_127;
int ps2_128;
int pe2_128;
int ps2_129;
int pe2_129;
int ps2_130;
int pe2_130;
int ps2_131;
int pe2_131;
int ps2_132;
int pe2_132;
int ps2_133;
int pe2_133;
int ps2_134;
int pe2_134;
int ps2_135;
int pe2_135;
int ps2_136;
int pe2_136;
int ps2_137;
int pe2_137;
int ps2_138;
int pe2_138;
int ps2_139;
int pe2_139;
int ps2_140;
int pe2_140;
int ps2_141;
int pe2_141;
int ps2_142;
int pe2_142;
int ps2_143;
int pe2_143;
int ps2_144;
int pe2_144;
int ps2_145;
int pe2_145;
int kalibre;
int ps2_146;
int pe2_146;
int kalibre1;
int Exp02_Sen0_Val_02;
int Exp02_Sen0_Filter_02;
int Exp02_Sen0_Satus_02;
int Exp02_Sen1_Val_02;
int Exp02_Sen1_Filter_02;
int Exp02_Sen1_Satus_02;
int Exp02_Sen2_Val_02;
int Exp02_Sen2_Filter_02;
int Exp02_Sen2_Satus_02;
int Exp02_Sen3_Val_02;
int Exp02_Sen3_Filter_02;
int Exp02_Sen3_Satus_02;
} var_Int;
U8  SB5Esk;
U8  SB80Esk;
U8  SB81Esk;
U8  SB1SnEsk;
struct{
unsigned char CPU_Osc_1ms;
unsigned char CPU_Osc_10ms;
unsigned char CPU_Osc_100ms;
unsigned char CPU_Osc_500ms;
unsigned char CPU_Osc_1000ms;
unsigned char vana1;
unsigned char vana2;
unsigned char vana3;
unsigned char vana4;
unsigned char vana5;
unsigned char vana6;
unsigned char vana7;
unsigned char vana8;
unsigned char dummydeg_gmt_0;
unsigned char dummydeg_gmt_1;
unsigned char dummydeg_gmt_2;
} var_bit;
struct{
} var_Byte;
struct{
unsigned short CPU_InpWord;
unsigned short CPU_OutWord;
unsigned short CPU_OutWordHlp;
unsigned short R1_humidity1;
unsigned short R1_temp1;
unsigned short R1_ec;
unsigned short R1_salt;
unsigned short R2_humidity2;
unsigned short R2_temp2;
unsigned short R2_ec;
unsigned short R2_salt;
unsigned short R3_humidity3;
unsigned short R3_temp3;
unsigned short R3_ec;
unsigned short R3_salt;
unsigned short R4_humidity4;
unsigned short R4_temp4;
unsigned short R4_ec;
unsigned short R4_salt;
unsigned short R5_humidity5;
unsigned short R5_temp5;
unsigned short R5_ec;
unsigned short R5_salt;
unsigned short R6_humidity6;
unsigned short R6_temp6;
unsigned short R6_ec;
unsigned short R6_salt;
unsigned short R7_humidity7;
unsigned short R7_temp7;
unsigned short R7_ec;
unsigned short R7_salt;
unsigned short R8_humidity8;
unsigned short R8_temp8;
unsigned short R8_ec;
unsigned short R8_salt;
unsigned short R9_humidity9;
unsigned short R9_temp9;
unsigned short R9_ec;
unsigned short R9_salt;
unsigned short R10_humidity10;
unsigned short R10_temp10;
unsigned short R10_ec;
unsigned short R10_salt;
unsigned short R11_humidity11;
unsigned short R11_temp11;
unsigned short R11_ec;
unsigned short R11_salt;
unsigned short R12_humidity12;
unsigned short R12_temp12;
unsigned short R12_ec;
unsigned short R12_salt;
unsigned short R13_humidity13;
unsigned short R13_temp13;
unsigned short R13_ec;
unsigned short R13_salt;
unsigned short R14_humidity14;
unsigned short R14_temp14;
unsigned short R14_ec;
unsigned short R14_salt;
unsigned short R15_humidity15;
unsigned short R15_temp15;
unsigned short R15_ec;
unsigned short R15_salt;
unsigned short R16_humidity16;
unsigned short R16_temp16;
unsigned short R16_ec;
unsigned short R16_salt;
unsigned short R17_humidity17;
unsigned short R17_temp17;
unsigned short R17_ec;
unsigned short R17_salt;
unsigned short R18_humidity18;
unsigned short R18_temp18;
unsigned short R18_ec;
unsigned short R18_salt;
unsigned short R19_humidity19;
unsigned short R19_temp19;
unsigned short R19_ec;
unsigned short R19_salt;
unsigned short R20_humidity20;
unsigned short R20_temp20;
unsigned short R20_ec;
unsigned short R20_salt;
unsigned short R21_humidity21;
unsigned short R21_temp21;
unsigned short R21_ec;
unsigned short R21_salt;
unsigned short R22_humidity22;
unsigned short R22_temp22;
unsigned short R22_ec;
unsigned short R22_salt;
unsigned short R23_humidity23;
unsigned short R23_temp23;
unsigned short R23_ec;
unsigned short R23_salt;
unsigned short R24_humidity24;
unsigned short R24_temp24;
unsigned short R24_ec;
unsigned short R24_salt;
unsigned short R1_L_humidity101;
unsigned short R1_L_temp101;
unsigned short R2_L_humidity102;
unsigned short R2_L_temp102;
unsigned short R3_L_humidity103;
unsigned short R3_L_temp103;
unsigned short R4_L_humidity104;
unsigned short R4_L_temp104;
unsigned short R5_L_humidity105;
unsigned short R5_L_temp105;
unsigned short R6_L_humidity106;
unsigned short R6_L_temp106;
unsigned short R7_L_humidity107;
unsigned short R7_L_temp107;
unsigned short R8_L_humidity108;
unsigned short R8_L_temp108;
unsigned short R9_L_humidity109;
unsigned short R9_L_temp109;
unsigned short R10_L_humidity110;
unsigned short R10_L_temp110;
unsigned short R11_L_humidity111;
unsigned short R11_L_temp111;
unsigned short R12_L_humidity112;
unsigned short R12_L_temp112;
unsigned short R13_L_humidity113;
unsigned short R13_L_temp113;
unsigned short R14_L_humidity114;
unsigned short R14_L_temp114;
unsigned short R15_L_humidity115;
unsigned short R15_L_temp115;
unsigned short R16_L_humidity116;
unsigned short R16_L_temp116;
unsigned short R17_L_humidity117;
unsigned short R17_L_temp117;
unsigned short R18_L_humidity118;
unsigned short R18_L_temp118;
unsigned short R19_L_humidity119;
unsigned short R19_L_temp119;
unsigned short R20_L_humidity120;
unsigned short R20_L_temp120;
unsigned short R21_L_humidity121;
unsigned short R21_L_temp121;
unsigned short R22_L_humidity122;
unsigned short R22_L_temp122;
unsigned short R23_L_humidity123;
unsigned short R23_L_temp123;
unsigned short R24_L_humidity124;
unsigned short R24_L_temp124;
unsigned short R1_salt_co;
unsigned short R1_ec1;
unsigned short kal;
unsigned short ortlama_1_9;
unsigned short ortlama_1_9_20;
unsigned short son_ortlama_1_9_20;
unsigned short ortlama_3_9_17;
unsigned short son_ortlama_3_9_17;
unsigned short ortlama_1_9_17;
unsigned short son_ortlama_1_9_17;
unsigned short ortlama_2_10;
unsigned short ortlama_2_10_18;
unsigned short son_ortlama_2_10_18;
unsigned short ortlama_3_11;
unsigned short ortlama_3_11_19;
unsigned short son_ortlama_3_11_19;
unsigned short son_ortlama_3;
unsigned short ortlama_4_12;
unsigned short ortlama_4_12_20;
unsigned short son_ortlama_4_12_20;
unsigned short ortlama_5_13;
unsigned short ortlama_5_13_21;
unsigned short son_ortlama_5_13_20;
unsigned short son_ortlama_5_13_21;
unsigned short ortlama_6_14;
unsigned short ortlama_6_14_22;
unsigned short son_ortlama_6_14_22;
unsigned short R115_humidity;
unsigned short ortlama_7_15;
unsigned short ortlama_7_15_23;
unsigned short son_ortlama_7_15_23;
unsigned short ortlama_8_16;
unsigned short ortlama_8_16_24;
unsigned short son_ortlama_8_16_24;
unsigned short Exp01_InpWord_01;
unsigned short Exp01_OutWord_01;
unsigned short Exp01_OutWordHlp_01;
unsigned char dummydeg_gmt_3;
unsigned char dummydeg_gmt_4;
unsigned char dummydeg_gmt_5;
unsigned char dummydeg_gmt_6;
} var_Word;
struct{
} var_DWord;
struct{
float R1_humidity;
float R1_temp;
float R1_L_humidity;
float R1_L_temp;
float R2_humidity;
float R2_temp;
float R2_L_humidity;
float R2_L_temp;
float R3_humidity;
float R3_temp;
float R3_L_humidity;
float R3_L_temp;
float R4_humidity;
float R4_temp;
float R4_L_humidity;
float R4_L_temp;
float R5_humidity;
float R5_temp;
float R5_L_humidity;
float R5_L_temp;
float R6_humidity;
float R6_temp;
float R6_L_humidity;
float R6_L_temp;
float R7_humidity;
float R7_temp;
float R7_L_humidity;
float R7_L_temp;
float R8_humidity;
float R8_temp;
float R8_L_humidity;
float R8_L_temp;
float R9_humidity;
float R9_temp;
float R9_L_humidity;
float R9_L_temp;
float R10_humidity;
float R10_temp;
float R10_L_humidity;
float R10_L_temp;
float R11_humidity;
float R11_temp;
float R11_L_humidity;
float R11_L_temp;
float R12_humidity;
float R12_temp;
float R12_L_humidity;
float R12_L_temp;
float R13_humidity;
float R13_temp;
float R13_L_humidity;
float R13_L_temp;
float R14_humidity;
float R14_temp;
float R14_L_humidity;
float R14_L_temp;
float R15_humidity;
float R15_temp;
float R15_L_humidity;
float R15_L_temp;
float R16_humidity;
float R16_temp;
float R16_L_humidity;
float R16_L_temp;
float R17_humidity;
float R17_temp;
float R17_L_humidity;
float R17_L_temp;
float R18_humidity;
float R18_temp;
float R18_L_humidity;
float R18_L_temp;
float R19_humidity;
float R19_temp;
float R19_L_humidity;
float R19_L_temp;
float R20_humidity;
float R20_temp;
float R20_L_humidity;
float R20_L_temp;
float R21_humidity;
float R21_temp;
float R21_L_humidity;
float R21_L_temp;
float R22_humidity;
float R22_temp;
float R22_L_humidity;
float R22_L_temp;
float R23_humidity;
float R23_temp;
float R23_L_humidity;
float R23_L_temp;
float R24_humidity;
float R24_temp;
float R24_L_humidity;
float R24_L_temp;
float R1_salt1;
float kal1;
unsigned char dummydeg_gmt_7;
unsigned char dummydeg_gmt_8;
unsigned char dummydeg_gmt_9;
unsigned char dummydeg_gmt_10;
} var_float;
unsigned char gmtfn1;

unsigned char gmtfn10;

unsigned char gmtfn100;

unsigned char gmtfn103;

unsigned char gmtfn104;

unsigned char gmtfn105;

unsigned char gmtfn108;

unsigned char gmtfn109;

unsigned char gmtfn110;

unsigned char gmtfn113;

unsigned char gmtfn114;

unsigned char gmtfn115;

unsigned char gmtfn118;

unsigned char gmtfn119;

unsigned char gmtfn120;

unsigned char gmtfn123;

unsigned char gmtfn124;

unsigned char gmtfn125;

unsigned char gmtfn13;

unsigned char gmtfn132;

unsigned char gmtfn133;

unsigned char gmtfn134;

unsigned char gmtfn14;

unsigned char gmtfn141;

unsigned char gmtfn142;

unsigned char gmtfn143;

unsigned char gmtfn15;

unsigned char gmtfn150;

unsigned char gmtfn151;

unsigned char gmtfn152;

unsigned char gmtfn159;

unsigned char gmtfn160;

unsigned char gmtfn161;

unsigned char gmtfn168;

unsigned char gmtfn169;

unsigned char gmtfn170;

unsigned char gmtfn177;

unsigned char gmtfn178;

unsigned char gmtfn179;

unsigned char gmtfn18;

unsigned char gmtfn186;

unsigned char gmtfn187;

unsigned char gmtfn188;

unsigned char gmtfn19;

unsigned char gmtfn2;

unsigned char gmtfn20;

unsigned char gmtfn23;

unsigned char gmtfn24;

unsigned char gmtfn25;

unsigned char gmtfn28;

unsigned char gmtfn29;

unsigned char gmtfn3;

unsigned char gmtfn30;

unsigned char gmtfn33;

unsigned char gmtfn34;

unsigned char gmtfn35;

unsigned char gmtfn38;

unsigned char gmtfn39;

unsigned char gmtfn4;

unsigned char gmtfn40;

unsigned char gmtfn43;

unsigned char gmtfn44;

unsigned char gmtfn45;

unsigned char gmtfn48;

unsigned char gmtfn49;

unsigned char gmtfn5;

unsigned char gmtfn50;

unsigned char gmtfn53;

unsigned char gmtfn54;

unsigned char gmtfn55;

unsigned char gmtfn58;

unsigned char gmtfn59;

unsigned char gmtfn60;

unsigned char gmtfn63;

unsigned char gmtfn64;

unsigned char gmtfn65;

unsigned char gmtfn68;

unsigned char gmtfn69;

unsigned char gmtfn7;

unsigned char gmtfn70;

unsigned char gmtfn73;

unsigned char gmtfn74;

unsigned char gmtfn75;

unsigned char gmtfn78;

unsigned char gmtfn79;

unsigned char gmtfn8;

unsigned char gmtfn80;

unsigned char gmtfn83;

unsigned char gmtfn84;

unsigned char gmtfn85;

unsigned char gmtfn88;

unsigned char gmtfn89;

unsigned char gmtfn9;

unsigned char gmtfn90;

unsigned char gmtfn93;

unsigned char gmtfn94;

unsigned char gmtfn95;

unsigned char gmtfn98;

unsigned char gmtfn99;



} plcvar_t;


#ifndef PLC_SIM
// PLC variables
plcvar_t plcvar;
// memory dedicated macros
#define MEM_GETADDR(x)			((I32)&(plcvar.x))
#define MEM_GETVALUE(x)			(plcvar.x)
#define MEM_GETVALUE(x)			(plcvar.x)
#define MEM_GETSIZE(x)			(sizeof(plcvar.x))
#else
// PLC variables
plcvar_t *plcvar;

// memory dedicated macros
#define MEM_GETADDR(x)			((I32)&(plcvar->x))
#define MEM_GETVALUE(x)			(plcvar->x)
#define MEM_GETSIZE(x)			(sizeof(plcvar->x))
#endif

/*
*********************************************************************************************************
*                                            LOCAL MACROS
*********************************************************************************************************
*/

// driver access macros
#define DRV_OPEN(id,flags)		(drvif->open(id,flags))
#define DRV_CLOSE(id)			(drvif->close(id))
#define DRV_READ(id,buf,size)	(drvif->read(id,buf,size))
#define DRV_WRITE(id,buf,size)	(drvif->write(id,buf,size))
#define DRV_IOCTL(id,req,val)	(drvif->ioctl(id,req,val))
#define DRV_CONNECT(id,sig,cb)	(drvif->connect(id,sig,cb))

// library access macros
#define LIB_OPEN(id,flags)		(libif->open(id,flags))
#define LIB_CLOSE(id)			(libif->close(id))
#define LIB_READ(id,buf,size)	(libif->read(id,buf,size))
#define LIB_WRITE(id,buf,size)	(libif->write(id,buf,size))
#define LIB_IOCTL(id,req,val)	(libif->ioctl(id,req,val))
#define LIB_SNPRINTF(buf,size,frmt, ...) (libif->snprintf(buf,size,frmt, __VA_ARGS__))

// PLC application specific macros
#define APP_GET_ENTRY()			(app_entry_point)
#define APP_SET_ENTRY(x)		(app_entry_point=x)
#define APP_GET_FNADDR(f)		(((U32)f)+APP_GET_ENTRY())
#define APP_GET_VRADDR(v)		(((U32)v)+APP_GET_ENTRY())


/*
*********************************************************************************************************
*                                       EXTERNAL FUNCTIONS DECLERATION
*********************************************************************************************************
*/

#ifdef PLC_SIM
extern void libif_init(libif_t *library_interface);
extern void lib_math_update	(int *vals, int size);
extern void lib_mem_update	(int *vals, int size);

extern void drvif_init(drvif_t *driver_interface);
extern void drv_din_update	(int *vals, int size);
extern void drv_dout_update	(int *vals, int size);
extern void drv_ain_update	(int *vals, int size);
extern void drv_aout_update	(int *vals, int size);
extern void drv_sen_update	(int *vals, int size);
extern void drv_ldc_update	(int *vals, int size);
extern void drv_enc_update	(int *vals, int size);
extern void drv_hso_update	(int *vals, int size);
extern void drv_exp_update	(int *vals, int size);
extern void drv_rtc_update	(int *vals, int size);
extern void drv_com_update	(int *vals, int size);
extern void drv_wmi_update	(int *vals, int size);
extern void drv_pid_update	(int *vals, int size);
#endif //PLC_SIM


/*
*********************************************************************************************************
*                                       		APP ABI INTERFACE
*********************************************************************************************************
*/

// Linker added symbols
#ifndef PLC_SIM
// Linker added symbols
extern U32 * _abi_start;
extern U32 * _data_loadaddr;
extern U32 * _data_start;
extern U32 * _data_end;
extern U32 * _bss_end;
extern U32 * _sstart;
extern load_fp_t _pa_start,  _pa_end;
extern load_fp_t _ia_start,  _ia_end;
extern load_fp_t _fia_start, _fia_end;


__attribute__ ((section(".app_abi_sec"))) app_abi_t gmtplc_abi =
{
	// Entry point
    .entry          = app_main,


    // Startup interface
    .sstart         = (U32*)&_sstart,
    .data_loadaddr  = (U32*)&_data_loadaddr,
    .data_start     = (U32*)&_data_start,
    .data_end       = (U32*)&_data_end,
    .bss_end        = (U32*)&_bss_end,
    .pa_start       = &_pa_start,
    .pa_end         = &_pa_end,
    .ia_start       = &_ia_start,
    .ia_end         = &_ia_end,
    .fia_start      = &_fia_start,
    .fia_end        = &_fia_end,
};
#else
__attribute__ ((section(".app_abi_sec"))) app_abi_t gmtplc_abi =
{
	// Entry point
    .entry          = app_main,

    // Startup interface
    .sstart         = (U32*)0,
    .data_loadaddr  = (U32*)0,
    .data_start     = (U32*)0,
    .data_end       = (U32*)0,
    .bss_end        = (U32*)0,
    .pa_start       = 0,
    .pa_end         = 0,
    .ia_start       = 0,
    .ia_end         = 0,
    .fia_start      = 0,
    .fia_end        = 0,

};
#endif //!PLC_SIM


void cl_fModulinit(void);
void cl_fPIDCompile(void);
void cl_fReadFromFlash(void);
void cl_FSetFromPowerOn(void);
void cl_FPowerOnFunction(void);


unsigned short cl_fGetWord(unsigned char d0,unsigned char d1,unsigned char d2,unsigned char d3,unsigned char d4,unsigned char d5,unsigned char d6,unsigned char d7,unsigned char d8,unsigned char d9,unsigned char d10,unsigned char d11,unsigned char d12,unsigned char d13,unsigned char d14,unsigned char d15)
{
unsigned short sn1 =0;
sn1 += (d0 * 1);
sn1 += (d1 * 2);
sn1 += (d2 * 4);
sn1 += (d3 * 8);
sn1 += (d4 * 16);
sn1 += (d5 * 32);
sn1 += (d6 * 64);
sn1 += (d7 * 128);	
sn1 += (d8 * 256);
sn1 += (d9 * 512);
sn1 += (d10 * 1024);
sn1 += (d11 * 2048);
sn1 += (d12 * 4096);
sn1 += (d13 * 8192);
sn1 += (d14 * 16384);
sn1 += (d15 * 32768);
return sn1;			
}



void cl_fSetWord(unsigned short *deg, unsigned short *old , unsigned char *d0,unsigned char *d1,unsigned char *d2,unsigned char *d3,unsigned char *d4,unsigned char *d5,unsigned char *d6,unsigned char *d7,unsigned char *d8,unsigned char *d9,unsigned char *d10,unsigned char *d11,unsigned char *d12,unsigned char *d13,unsigned char *d14,unsigned char *d15)
{
unsigned short sn1 =0;
if (d0 != NULL)
 sn1 += (*d0 * 1);
if (d1 != NULL)
 sn1 += (*d1 * 2);
if (d2 != NULL)
 sn1 += (*d2 * 4);
if (d3 != NULL)
 sn1 += (*d3 * 8);
if (d4 != NULL)
 sn1 += (*d4 * 16);
if (d5 != NULL)
 sn1 += (*d5 * 32);
if (d6 != NULL)
 sn1 += (*d6 * 64);
if (d7 != NULL)
 sn1 += (*d7 * 128);
if (d8 != NULL)
 sn1 += (*d8 * 256);
if (d9 != NULL)
 sn1 += (*d9 * 512);
if (d10 != NULL)
 sn1 += (*d10 * 1024);
if (d11 != NULL)
 sn1 += (*d11 * 2048);
if (d12 != NULL)
 sn1 += (*d12 * 4096);
if (d13 != NULL)
 sn1 += (*d13 * 8192);
if (d14 != NULL)
 sn1 += (*d14 * 16384);
if (d15 != NULL)
 sn1 += (*d15 * 32768);

if (*deg != *old )
{
  *old=*deg;
 if (d0 != NULL)
  *d0= (*deg >> 0) & 1;
 if (d1 != NULL)
  *d1= (*deg >> 1) & 1;
 if (d2 != NULL)
  *d2= (*deg >> 2) & 1;
 if (d3 != NULL)
  *d3= (*deg >> 3) & 1;
 if (d4 != NULL)
  *d4= (*deg >> 4) & 1;
 if (d5 != NULL)
  *d5= (*deg >> 5) & 1;
 if (d6 != NULL)
  *d6= (*deg >> 6) & 1;
 if (d7 != NULL)
  *d7= (*deg >> 7) & 1;
 if (d8 != NULL)
  *d8= (*deg >> 8) & 1;
 if (d9 != NULL)
  *d9= (*deg >> 9) & 1;
 if (d10 != NULL)
  *d10= (*deg >> 10) & 1;
 if (d11 != NULL)
  *d11= (*deg >> 11) & 1;
 if (d12 != NULL)
  *d12= (*deg >> 12) & 1;
 if (d13 != NULL)
  *d13= (*deg >> 13) & 1;
 if (d14 != NULL)
  *d14= (*deg >> 14) & 1;
 if (d15 != NULL)
  *d15= (*deg >> 15) & 1;
}
else
{
  if (sn1 != *deg)
  {
    *deg= sn1;
    *old= sn1;
  }
}

}


/*******************************************************************************
* Function Name  : app_main
* Description    : Do not modify !!!
* Input          : None
* Output         : None
* Return         : None
*******************************************************************************/
void app_main(U32 app_addr)
{
		// assign the application start address
	APP_SET_ENTRY(app_addr);

	// assign the application interface variable address
	plcif.QP      = (U8*)MEM_GETADDR(QP[0]);
	plcif.IP      = (U8*)MEM_GETADDR(IP[0]);
//	plcif.QP_force      = (U8*)MEM_GETADDR(QP_Force0[0]);
//	plcif.IP_force      = (U8*)MEM_GETADDR(IP_Force0[0]);
	plcif.QP_force      = (U8*)MEM_GETADDR(QP[0]);
	plcif.IP_force      = (U8*)MEM_GETADDR(IP[0]);
	
	
	plcif.IP_prev = IP_prev;
	plcif.IP_filt = IP_filt;
	plcif.SI      = SI;
	plcif.SB      = SB;
#ifndef PLC_SIM
	plcif.RAMAddr = (U32)&plcvar;
    plcif.ABIStart = (U32)&_abi_start;
#else
	plcif.RAMAddr = (U32)plcvar;
    plcif.ABIStart = 0;
#endif
	plcif.MemAddr = 0;
	plcif.MemLen  = 0;
    plcif.InitAddr = APP_GET_FNADDR(cl_FSetFromPowerOn);
//    plcif.PowerOnAddr = APP_GET_FNADDR(cl_FPowerOnFunction);
    plcif.PowerOnAddr = APP_GET_FNADDR(cl_fReadFromFlash);
	

	// assign the system variables
#ifndef PLC_SIM
	appif = (appif_t*) APPIF_ADDR;
	drvif = (drvif_t*) DRVIF_ADDR;
	libif = (libif_t*) LIBIF_ADDR;
#else
	appif = (appif_t*) &my_appif;
	drvif = (drvif_t*) &my_drvif;
	libif = (libif_t*) &my_libif;
#endif //PLC_SIM

	// assign the application functions
	appif->init  = (app_func_t) APP_GET_FNADDR(app_init);
	appif->exit  = (app_func_t) APP_GET_FNADDR(app_exit);
	appif->proc  = (app_func_t) APP_GET_FNADDR(app_proc);
	appif->plcif = &plcif;
}//app_main


/*******************************************************************************
* Function Name  : event_din_onchanged
* Description    : Digital input OnChanged event.
* Input          : None
* Output         : None
* Return         : None
*******************************************************************************/
void event_din_onchanged(void)
{
}//event_din_onchanged


/*******************************************************************************
* Function Name  : event_enc_onfinished
* Description    : Encoder inputs OnFinished event.
* Input          : None
* Output         : None
* Return         : None
*******************************************************************************/
void event_enc_onfinished(U32 chan, U32 count)
{
}//event_enc_onfinished


/*******************************************************************************
* Function Name  : app_exit
* Description    : De-initialize the application.
* 				   Do not change the name of function !!!
* Input          : None
* Output         : None
* Return         : None
*******************************************************************************/
int app_exit(void)
{
	//---------------------------------------------------------------
	// Close the driver files
	//---------------------------------------------------------------

	// close digital input driver
	DRV_CLOSE(din);

	// close digital output driver
	DRV_CLOSE(dout);

	// close analog input driver
	DRV_CLOSE(ain);

	// close analog output driver
	DRV_CLOSE(aout);

	// close sensor input driver
	DRV_CLOSE(sen);

	// close load-cell input driver
	DRV_CLOSE(ldc);

	// close high speed output driver
	DRV_CLOSE(hso);

	// close encoder input driver
	DRV_CLOSE(enc);

	// close expansion modules driver
	DRV_CLOSE(gxm);

	// close RTC driver
	DRV_CLOSE(rtc);

	// close Communication driver
	DRV_CLOSE(com);

	// close WMI driver
	DRV_CLOSE(wmi);

	// close PID driver
	DRV_CLOSE(pid);

	//---------------------------------------------------------------
	// Close the library files
	//---------------------------------------------------------------

	// close Mathematics library driver
	LIB_CLOSE(math);

	// close memory library driver
	LIB_CLOSE(memi);

	return 1;
}//app_exit

void cl_FSetValuesTemplates(void);

/*******************************************************************************
* Function Name  : app_init
* Description    : Initialize the application.
* 				   Do not change the name of function !!!
* Input          : None
* Output         : None
* Return         : None
*******************************************************************************/
int app_init(void)
{
	#ifdef PLC_SIM
	plcvar_t *mem = plcvar;
	#else
	plcvar_t *mem = &plcvar;
	#endif //PLC_SIM

	I32 params[16];

#ifndef PLC_SIM
	plcif.RAMAddr = (U32)&plcvar;
#else
	plcif.RAMAddr = (U32)plcvar;
#endif
	
	// initialize the memory address
	plcif.MemAddr = mem_flash;
	plcif.MemLen  = (U32)sizeof(*mem);
	cl_fReadFromFlash();
    cl_vrunonce=1;
    cl_vrunonce2=1;
	
	dummydegisken=0;
   dummydegisken1=0;
   dummydegisken2=0;
   flash_dummy_degisken=0;
	
   //itialize the application parameters
	//SI[14] = 503;		// ModbusTCP slave port
	//SI[15] = 10000;		// ModbusTCP slave timeout
	SI[16] = 1000;		// ModbusRTU slave timeout (RS232)
	SI[17] = 1000;		// ModbusRTU slave timeout (RS485)
	
	SB[53]=0;
	SB[54]=0;
	SB[55]=0;
	
	din=-1;		// Digital inputs
    dout=-1;	// Digital outputs
	ain=-1;		// Analog inputs
    aout=-1;	// Analog outputs
    sen=-1;		// Sensor inputs
    ldc=-1;		// Load-cell inputs
    hso=-1;		// High speed outputs
	enc=-1;		// Encoder inputs
    gxm=-1;		// Expansion modules
    rtc=-1;		// RTC
	com=-1;		// Communication devices
	wmi=-1;		// WMI
    pid=-1;		// PID
    net=-1;		// PID
	
	
	//Reset All Force Vector
    for (int i=0; i<280; i++)
    {
        mem->IP_Force0[i] = 1;
        mem->IP_Force1[i] = 0;
    }//for	
	
	modb_array_init();

	// open the digital input driver
	if ((din = DRV_OPEN(DRIVER_DIN, 0)) != DRIVER_INVALID)
	{
		// set variable address and size
		params[0] = MEM_GETADDR(IP[0]);						// IP current values address
		params[1] = (I32)&IP_prev[0];						// IP previous values address
		params[2] = (I32)&IP_filt[0];						// IP filter values address
		params[3] = DIN_CHAN_SIZE;							// IP variables size
		params[4] = APP_GET_FNADDR(event_din_onchanged);	// Call-back event address
		DRV_IOCTL(din, IOCTL_DIN_INIT, params);
	}//if

	// open the digital output driver
	if ((dout = DRV_OPEN(DRIVER_DOUT, 0)) != DRIVER_INVALID)
	{
		// set variable address and size
		params[0] = MEM_GETADDR(QP[0]);						// QP values address
		params[1] = DOUT_CHAN_SIZE;							// QP variables size
		DRV_IOCTL(dout, IOCTL_DOUT_INIT, params);
	}//if

	cl_FSetFromPowerOn();
	cl_FSetValuesTemplates();
	
	    // open the expansion driver
    if ((gxm = DRV_OPEN(DRIVER_EXP, 0)) != DRIVER_INVALID)
    {
        U32 map_addr;
        U32 map_size;

        // get the map address and size
        get_module_info(&map_addr, &map_size);

        // set expansion driver parameters
        params[0] = APP_GET_VRADDR(map_addr);            	// Module map address
        params[1] = map_size;                             	// Module map item size
        DRV_IOCTL(gxm, IOCTL_EXP_INIT, params);

		// start the expansion state machine
		DRV_IOCTL(gxm, IOCTL_EXP_START, 0);
    }//if
	
	#if IMG_REVISION >= 523
	math = LIB_OPEN(LIBRARY_MATH, 0);

	#endif			
	
	
	// open the memory interface
    if ((memi = LIB_OPEN(LIBRARY_MEM, 0)) != LIBRARY_INVALID)
    {
		
        // Set the Modbus "coil" variables address
        params[0] = (U32)(addr_of_1byte_input);
        params[1] = 0;
        LIB_IOCTL(memi, IOCTL_MEM_SETVARINPUT, params);		
				
        // Set the Modbus "coil" variables address
        params[0] = (U32)(addr_of_1byte);
        params[1] = 0;
        LIB_IOCTL(memi, IOCTL_MEM_SETVARBIT, params);

        // Set the Modbus "word" variables address
        params[0] = (U32)(addr_of_2byte);
        params[1] = 0;
        LIB_IOCTL(memi, IOCTL_MEM_SETVARWORD, params);

        // Set the Modbus "integer" variables address
        params[0] = (U32)(addr_of_4byte);
        params[1] = 0;
        LIB_IOCTL(memi, IOCTL_MEM_SETVARINT, params);
    }//if	
	
	if ((wmi = DRV_OPEN(DRIVER_WMI, 0)) != DRIVER_INVALID)
	{		
		DRV_IOCTL(wmi, IOCTL_WMI_INIT, 0);
	}
	
	
	
	#if IMG_REVISION >= 516
 	DRV_OPEN(DRIVER_NVM, 0);
	#endif	
	
	
	#if IMG_REVISION >= 525	
	static const char *_serv   = "vercheck.gmtcontrol.com";
	params[1] = APP_GET_VRADDR(_serv);
	
	
	//U32 *_serv   =   0xca64a8c0; //mete
	//U32 *_serv   =   0x98ec26d1; //verchek
	//U32 *_serv   =   0xaa64a8c0; //abdullah
	//params[1] = (int) &_serv;
	
	
	I32 _port = 80;		
	//I32 _port = 5000;	
	params[0] = (int) &_port;
	
	I32 _dnsEnable = 1;
	params[2] = (int) &_dnsEnable;
	
	DRV_IOCTL(DRIVER_COM, IOCTL_COM_MAILINIT, params);
	#endif	
	
	
	
    // open the math interface

	
cl_FSetFromPowerOn();
addr_of_1byte[0] = (U32)(&mem->var_bit.vana1);
addr_of_1byte[1] = (U32)(&mem->var_bit.vana2);
addr_of_1byte[2] = (U32)(&mem->var_bit.vana3);
addr_of_1byte[3] = (U32)(&mem->var_bit.vana4);
addr_of_1byte[4] = (U32)(&mem->var_bit.vana5);
addr_of_1byte[5] = (U32)(&mem->var_bit.vana7);
addr_of_1byte[6] = (U32)(&mem->var_bit.vana6);
addr_of_1byte[7] = (U32)(&mem->var_bit.vana8);
addr_of_1byte[8] = (U32)(&mem->QP[0]);
addr_of_1byte[9] = (U32)(&mem->QP[1]);
addr_of_1byte[10] = (U32)(&mem->QP[23]);
addr_of_1byte[11] = (U32)(&mem->QP[22]);
addr_of_1byte[12] = (U32)(&mem->QP[2]);
addr_of_1byte[13] = (U32)(&mem->QP[3]);
addr_of_1byte[14] = (U32)(&mem->QP[4]);
addr_of_1byte[15] = (U32)(&mem->QP[5]);
addr_of_2byte[2] = (U32)(&mem->var_Word.R1_ec);
addr_of_2byte[3] = (U32)(&mem->var_Word.R1_salt);
addr_of_2byte[6] = (U32)(&mem->var_Word.R2_ec);
addr_of_2byte[7] = (U32)(&mem->var_Word.R2_salt);
addr_of_2byte[30] = (U32)(&mem->var_Word.R9_salt);
addr_of_2byte[31] = (U32)(&mem->var_Word.R8_salt);
addr_of_2byte[32] = (U32)(&mem->var_Word.R7_salt);
addr_of_2byte[33] = (U32)(&mem->var_Word.R6_salt);
addr_of_2byte[34] = (U32)(&mem->var_Word.R5_salt);
addr_of_2byte[35] = (U32)(&mem->var_Word.R4_salt);
addr_of_2byte[36] = (U32)(&mem->var_Word.R3_salt);
addr_of_2byte[37] = (U32)(&mem->var_Word.R24_salt);
addr_of_2byte[38] = (U32)(&mem->var_Word.R23_salt);
addr_of_2byte[39] = (U32)(&mem->var_Word.R22_salt);
addr_of_2byte[40] = (U32)(&mem->var_Word.R21_salt);
addr_of_2byte[41] = (U32)(&mem->var_Word.R20_salt);
addr_of_2byte[42] = (U32)(&mem->var_Word.R19_salt);
addr_of_2byte[43] = (U32)(&mem->var_Word.R18_salt);
addr_of_2byte[44] = (U32)(&mem->var_Word.R17_salt);
addr_of_2byte[45] = (U32)(&mem->var_Word.R16_salt);
addr_of_2byte[46] = (U32)(&mem->var_Word.R15_salt);
addr_of_2byte[47] = (U32)(&mem->var_Word.R14_salt);
addr_of_2byte[48] = (U32)(&mem->var_Word.R13_salt);
addr_of_2byte[49] = (U32)(&mem->var_Word.R12_salt);
addr_of_2byte[50] = (U32)(&mem->var_Word.R11_salt);
addr_of_2byte[51] = (U32)(&mem->var_Word.R10_salt);
addr_of_2byte[74] = (U32)(&mem->var_Word.R9_ec);
addr_of_2byte[75] = (U32)(&mem->var_Word.R8_ec);
addr_of_2byte[76] = (U32)(&mem->var_Word.R7_ec);
addr_of_2byte[77] = (U32)(&mem->var_Word.R6_ec);
addr_of_2byte[78] = (U32)(&mem->var_Word.R5_ec);
addr_of_2byte[79] = (U32)(&mem->var_Word.R4_ec);
addr_of_2byte[80] = (U32)(&mem->var_Word.R3_ec);
addr_of_2byte[81] = (U32)(&mem->var_Word.R24_ec);
addr_of_2byte[82] = (U32)(&mem->var_Word.R23_ec);
addr_of_2byte[83] = (U32)(&mem->var_Word.R22_ec);
addr_of_2byte[84] = (U32)(&mem->var_Word.R21_ec);
addr_of_2byte[85] = (U32)(&mem->var_Word.R20_ec);
addr_of_2byte[86] = (U32)(&mem->var_Word.R19_ec);
addr_of_2byte[87] = (U32)(&mem->var_Word.R18_ec);
addr_of_2byte[88] = (U32)(&mem->var_Word.R17_ec);
addr_of_2byte[89] = (U32)(&mem->var_Word.R16_ec);
addr_of_2byte[90] = (U32)(&mem->var_Word.R14_ec);
addr_of_2byte[91] = (U32)(&mem->var_Word.R15_ec);
addr_of_2byte[92] = (U32)(&mem->var_Word.R13_ec);
addr_of_2byte[93] = (U32)(&mem->var_Word.R12_ec);
addr_of_2byte[94] = (U32)(&mem->var_Word.R11_ec);
addr_of_2byte[95] = (U32)(&mem->var_Word.R10_ec);
addr_of_2byte[100] = (U32)(&mem->var_Word.son_ortlama_1_9_17);
addr_of_2byte[101] = (U32)(&mem->var_Word.son_ortlama_2_10_18);
addr_of_2byte[102] = (U32)(&mem->var_Word.son_ortlama_3_11_19);
addr_of_2byte[103] = (U32)(&mem->var_Word.son_ortlama_4_12_20);
addr_of_2byte[104] = (U32)(&mem->var_Word.son_ortlama_5_13_21);
addr_of_2byte[105] = (U32)(&mem->var_Word.son_ortlama_6_14_22);
addr_of_2byte[106] = (U32)(&mem->var_Word.son_ortlama_7_15_23);
addr_of_2byte[107] = (U32)(&mem->var_Word.son_ortlama_8_16_24);
addr_of_4byte[0] = (U32)(&mem->var_float.R1_humidity);
addr_of_4byte[1] = (U32)(&mem->var_float.R1_temp);
addr_of_4byte[2] = (U32)(&mem->var_float.R1_L_humidity);
addr_of_4byte[3] = (U32)(&mem->var_float.R1_L_temp);
addr_of_4byte[4] = (U32)(&mem->var_float.R2_humidity);
addr_of_4byte[5] = (U32)(&mem->var_float.R2_temp);
addr_of_4byte[6] = (U32)(&mem->var_float.R2_L_humidity);
addr_of_4byte[7] = (U32)(&mem->var_float.R2_L_temp);
addr_of_4byte[8] = (U32)(&mem->var_float.R3_humidity);
addr_of_4byte[9] = (U32)(&mem->var_float.R3_temp);
addr_of_4byte[10] = (U32)(&mem->var_float.R3_L_humidity);
addr_of_4byte[11] = (U32)(&mem->var_float.R3_L_temp);
addr_of_4byte[12] = (U32)(&mem->var_float.R4_humidity);
addr_of_4byte[13] = (U32)(&mem->var_float.R4_temp);
addr_of_4byte[14] = (U32)(&mem->var_float.R4_L_humidity);
addr_of_4byte[15] = (U32)(&mem->var_float.R4_L_temp);
addr_of_4byte[16] = (U32)(&mem->var_float.R5_humidity);
addr_of_4byte[17] = (U32)(&mem->var_float.R5_temp);
addr_of_4byte[18] = (U32)(&mem->var_float.R5_L_humidity);
addr_of_4byte[19] = (U32)(&mem->var_float.R5_L_temp);
addr_of_4byte[20] = (U32)(&mem->var_float.R6_humidity);
addr_of_4byte[21] = (U32)(&mem->var_float.R6_temp);
addr_of_4byte[22] = (U32)(&mem->var_float.R6_L_humidity);
addr_of_4byte[23] = (U32)(&mem->var_float.R6_L_temp);
addr_of_4byte[24] = (U32)(&mem->var_float.R7_humidity);
addr_of_4byte[25] = (U32)(&mem->var_float.R7_temp);
addr_of_4byte[26] = (U32)(&mem->var_float.R7_L_humidity);
addr_of_4byte[27] = (U32)(&mem->var_float.R7_L_temp);
addr_of_4byte[28] = (U32)(&mem->var_float.R8_humidity);
addr_of_4byte[29] = (U32)(&mem->var_float.R8_temp);
addr_of_4byte[30] = (U32)(&mem->var_float.R8_L_humidity);
addr_of_4byte[31] = (U32)(&mem->var_float.R8_L_temp);
addr_of_4byte[32] = (U32)(&mem->var_float.R9_humidity);
addr_of_4byte[33] = (U32)(&mem->var_float.R9_temp);
addr_of_4byte[34] = (U32)(&mem->var_float.R9_L_humidity);
addr_of_4byte[35] = (U32)(&mem->var_float.R9_L_temp);
addr_of_4byte[36] = (U32)(&mem->var_float.R10_humidity);
addr_of_4byte[37] = (U32)(&mem->var_float.R10_temp);
addr_of_4byte[38] = (U32)(&mem->var_float.R10_L_humidity);
addr_of_4byte[39] = (U32)(&mem->var_float.R10_L_temp);
addr_of_4byte[40] = (U32)(&mem->var_float.R11_humidity);
addr_of_4byte[41] = (U32)(&mem->var_float.R11_temp);
addr_of_4byte[42] = (U32)(&mem->var_float.R11_L_humidity);
addr_of_4byte[43] = (U32)(&mem->var_float.R11_L_temp);
addr_of_4byte[44] = (U32)(&mem->var_float.R12_humidity);
addr_of_4byte[45] = (U32)(&mem->var_float.R12_temp);
addr_of_4byte[46] = (U32)(&mem->var_float.R12_L_humidity);
addr_of_4byte[47] = (U32)(&mem->var_float.R12_L_temp);
addr_of_4byte[48] = (U32)(&mem->var_float.R13_humidity);
addr_of_4byte[49] = (U32)(&mem->var_float.R13_temp);
addr_of_4byte[50] = (U32)(&mem->var_float.R13_L_humidity);
addr_of_4byte[51] = (U32)(&mem->var_float.R13_L_temp);
addr_of_4byte[52] = (U32)(&mem->var_float.R14_humidity);
addr_of_4byte[53] = (U32)(&mem->var_float.R14_temp);
addr_of_4byte[54] = (U32)(&mem->var_float.R14_L_humidity);
addr_of_4byte[55] = (U32)(&mem->var_float.R14_L_temp);
addr_of_4byte[56] = (U32)(&mem->var_float.R15_humidity);
addr_of_4byte[57] = (U32)(&mem->var_float.R15_temp);
addr_of_4byte[58] = (U32)(&mem->var_float.R15_L_humidity);
addr_of_4byte[59] = (U32)(&mem->var_float.R15_L_temp);
addr_of_4byte[60] = (U32)(&mem->var_float.R16_humidity);
addr_of_4byte[61] = (U32)(&mem->var_float.R16_temp);
addr_of_4byte[62] = (U32)(&mem->var_float.R16_L_humidity);
addr_of_4byte[63] = (U32)(&mem->var_float.R16_L_temp);
addr_of_4byte[64] = (U32)(&mem->var_float.R17_humidity);
addr_of_4byte[65] = (U32)(&mem->var_float.R17_temp);
addr_of_4byte[66] = (U32)(&mem->var_float.R17_L_humidity);
addr_of_4byte[67] = (U32)(&mem->var_float.R17_L_temp);
addr_of_4byte[68] = (U32)(&mem->var_float.R18_humidity);
addr_of_4byte[69] = (U32)(&mem->var_float.R18_temp);
addr_of_4byte[70] = (U32)(&mem->var_float.R18_L_humidity);
addr_of_4byte[71] = (U32)(&mem->var_float.R18_L_temp);
addr_of_4byte[72] = (U32)(&mem->var_float.R19_humidity);
addr_of_4byte[73] = (U32)(&mem->var_float.R19_temp);
addr_of_4byte[74] = (U32)(&mem->var_float.R19_L_humidity);
addr_of_4byte[75] = (U32)(&mem->var_float.R19_L_temp);
addr_of_4byte[76] = (U32)(&mem->var_float.R20_humidity);
addr_of_4byte[77] = (U32)(&mem->var_float.R20_temp);
addr_of_4byte[78] = (U32)(&mem->var_float.R20_L_humidity);
addr_of_4byte[79] = (U32)(&mem->var_float.R20_L_temp);
addr_of_4byte[80] = (U32)(&mem->var_float.R21_humidity);
addr_of_4byte[81] = (U32)(&mem->var_float.R21_temp);
addr_of_4byte[82] = (U32)(&mem->var_float.R21_L_humidity);
addr_of_4byte[83] = (U32)(&mem->var_float.R21_L_temp);
addr_of_4byte[84] = (U32)(&mem->var_float.R22_humidity);
addr_of_4byte[85] = (U32)(&mem->var_float.R22_temp);
addr_of_4byte[86] = (U32)(&mem->var_float.R22_L_humidity);
addr_of_4byte[87] = (U32)(&mem->var_float.R22_L_temp);
addr_of_4byte[88] = (U32)(&mem->var_float.R23_humidity);
addr_of_4byte[89] = (U32)(&mem->var_float.R23_temp);
addr_of_4byte[90] = (U32)(&mem->var_float.R23_L_humidity);
addr_of_4byte[91] = (U32)(&mem->var_float.R23_L_temp);
addr_of_4byte[92] = (U32)(&mem->var_float.R24_humidity);
addr_of_4byte[93] = (U32)(&mem->var_float.R24_temp);
addr_of_4byte[94] = (U32)(&mem->var_float.R24_L_humidity);
addr_of_4byte[95] = (U32)(&mem->var_float.R24_L_temp);
IP_filt[0]=10;IP_filt[1]=10;IP_filt[2]=10;IP_filt[3]=10;IP_filt[4]=10;IP_filt[5]=10;IP_filt[6]=10;IP_filt[7]=10;IP_filt[8]=10;SI[14]=502;SI[15]=10000;IP_filt[16]=10;mem->QP[16]=0;IP_filt[17]=10;mem->QP[17]=0;IP_filt[18]=10;mem->QP[18]=0;IP_filt[19]=10;mem->QP[19]=0;IP_filt[20]=10;mem->QP[20]=0;IP_filt[21]=10;mem->QP[21]=0;IP_filt[22]=10;mem->QP[22]=0;IP_filt[23]=10;mem->QP[23]=0;return 1;
}//app_init
void cl_FSetValuesTemplates(void){
  #ifdef PLC_SIM
  plcvar_t *mem = plcvar;
  #else
  plcvar_t *mem = &plcvar;
  #endif //PLC_SIM

















































































































































































































plcif.MemLen  =3379;
}
void cl_FPowerOnFunction(void)
{
  #ifdef PLC_SIM
  plcvar_t *mem = plcvar;
  #else
  plcvar_t *mem = &plcvar;
  #endif //PLC_SIM
  cl_FSetFromPowerOn();
  cl_fModulinit();
  cl_fPIDCompile();
}
void cl_FSetFromPowerOn(void)
{
  #ifdef PLC_SIM
  plcvar_t *mem = plcvar;
  #else
  plcvar_t *mem = &plcvar;
  #endif //PLC_SIM
mem->plc_lad_delay_sayac=0;
mem->var_Word.CPU_InpWord = 0;
mem->var_Word.CPU_OutWord = 0;
mem->var_Word.CPU_OutWordHlp = 0;
mem->var_Int.CPU_HSC0_Dir = 0;
mem->var_Int.CPU_HSC0_Freq = 0;
mem->var_Int.CPU_HSC0_FreqPer = 1;
mem->var_Int.CPU_HSC1_Dir = 0;
mem->var_Int.CPU_HSC1_Freq = 0;
mem->var_Int.CPU_HSC1_FreqPer = 1;
mem->var_Int.CPU_HSC2_Dir = 0;
mem->var_Int.CPU_HSC2_Freq = 0;
mem->var_Int.CPU_HSC2_FreqPer = 1;
mem->var_Int.CPU_COM1_NetID = 1;
mem->var_Int.CPU_COM1_Timeout = 300;
mem->var_Int.CPU_COM1_ETX = 0;
mem->var_Int.CPU_COM1_Status = 0;
mem->var_Int.CPU_COM1_ErrVal = 0;
mem->var_Int.CPU_COM1_BufferByteAdet = 0;
mem->var_Int.CPU_COM2_NetID = 1;
mem->var_Int.CPU_COM2_Timeout = 300;
mem->var_Int.CPU_COM2_ETX = 0;
mem->var_Int.CPU_COM2_Status = 0;
mem->var_Int.CPU_COM2_ErrVal = 0;
mem->var_Int.CPU_COM2_BufferByteAdet = 0;
mem->var_Int.CPU_Eth_slave_timeout = 1000;
mem->var_Int.CPU_SlvDev0_timeout = 1000;
mem->var_Int.CPU_SlvDev1_timeout = 1000;
mem->var_Int.CPU_SlvDev2_timeout = 1000;
mem->var_Int.CPU_SlvDev3_timeout = 1000;
mem->var_Int.CPU_SlvDev4_timeout = 1000;
mem->var_bit.CPU_Osc_1ms = 0;
mem->var_bit.CPU_Osc_10ms = 0;
mem->var_bit.CPU_Osc_100ms = 0;
mem->var_bit.CPU_Osc_500ms = 0;
mem->var_bit.CPU_Osc_1000ms = 0;
mem->var_Int.CPU_LadderFreq = 0;
mem->var_Int.CPU_WMIStatus = 0;
mem->var_Int.pe2_0 = 1;
mem->var_Int.pe2_1 = 1;
mem->var_Int.pe2_2 = 1;
mem->var_Int.pe2_3 = 1;
mem->var_Int.pe2_5 = 1;
mem->var_Int.pe2_6 = 1;
mem->var_Int.pe2_7 = 1;
mem->var_Int.pe2_8 = 1;
mem->var_Int.pe2_9 = 1;
mem->var_Int.pe2_10 = 1;
mem->var_Int.pe2_11 = 1;
mem->var_Int.pe2_12 = 1;
mem->var_Int.pe2_13 = 1;
mem->var_Int.pe2_14 = 1;
mem->var_Int.pe2_15 = 1;
mem->var_Int.pe2_16 = 1;
mem->var_Int.pe2_17 = 1;
mem->var_Int.pe2_18 = 1;
mem->var_Int.pe2_19 = 1;
mem->var_Int.pe2_20 = 1;
mem->var_Int.pe2_21 = 1;
mem->var_Int.pe2_22 = 1;
mem->var_Int.pe2_23 = 1;
mem->var_Int.pe2_24 = 1;
mem->var_Int.pe2_25 = 1;
mem->var_Int.pe2_26 = 1;
mem->var_Int.pe2_27 = 1;
mem->var_Int.pe2_28 = 1;
mem->var_Int.pe2_29 = 1;
mem->var_Int.pe2_30 = 1;
mem->var_Int.pe2_31 = 1;
mem->var_Int.pe2_32 = 1;
mem->var_Int.pe2_33 = 1;
mem->var_Int.pe2_34 = 1;
mem->var_Int.pe2_35 = 1;
mem->var_Int.pe2_36 = 1;
mem->var_Int.pe2_37 = 1;
mem->var_Int.pe2_38 = 1;
mem->var_Int.pe2_39 = 1;
mem->var_Int.pe2_40 = 1;
mem->var_Int.pe2_41 = 1;
mem->var_Int.pe2_42 = 1;
mem->var_Int.pe2_43 = 1;
mem->var_Int.pe2_44 = 1;
mem->var_Int.pe2_45 = 1;
mem->var_Int.pe2_46 = 1;
mem->var_Int.pe2_47 = 1;
mem->var_Int.pe2_48 = 1;
mem->var_Int.pe2_49 = 1;
mem->var_Int.pe2_50 = 1;
mem->var_Int.pe2_51 = 1;
mem->var_Int.pe2_52 = 1;
mem->var_Int.pe2_53 = 1;
mem->var_Int.pe2_54 = 1;
mem->var_Int.pe2_55 = 1;
mem->var_Int.pe2_56 = 1;
mem->var_Int.pe2_57 = 1;
mem->var_Int.pe2_58 = 1;
mem->var_Int.pe2_59 = 1;
mem->var_Int.pe2_60 = 1;
mem->var_Int.pe2_61 = 1;
mem->var_Int.pe2_62 = 1;
mem->var_Int.pe2_63 = 1;
mem->var_Int.pe2_64 = 1;
mem->var_Int.pe2_65 = 1;
mem->var_Int.pe2_66 = 1;
mem->var_Int.pe2_67 = 1;
mem->var_Int.pe2_68 = 1;
mem->var_Int.pe2_69 = 1;
mem->var_Int.pe2_70 = 1;
mem->var_Int.pe2_71 = 1;
mem->var_Int.pe2_72 = 1;
mem->var_Int.pe2_73 = 1;
mem->var_Int.pe2_74 = 1;
mem->var_Int.pe2_75 = 1;
mem->var_Int.pe2_76 = 1;
mem->var_Int.pe2_77 = 1;
mem->var_Int.pe2_78 = 1;
mem->var_Int.pe2_79 = 1;
mem->var_Int.pe2_80 = 1;
mem->var_Int.pe2_81 = 1;
mem->var_Int.pe2_82 = 1;
mem->var_Int.pe2_83 = 1;
mem->var_Int.pe2_84 = 1;
mem->var_Int.pe2_85 = 1;
mem->var_Int.pe2_86 = 1;
mem->var_Int.pe2_87 = 1;
mem->var_Int.pe2_88 = 1;
mem->var_Int.pe2_89 = 1;
mem->var_Int.pe2_90 = 1;
mem->var_Int.pe2_91 = 1;
mem->var_Int.pe2_92 = 1;
mem->var_Int.pe2_93 = 1;
mem->var_Int.pe2_94 = 1;
mem->var_Int.pe2_95 = 1;
mem->var_Int.pe2_96 = 1;
mem->var_Int.pe2_97 = 1;
mem->var_Int.pe2_98 = 1;
mem->var_Int.pe2_99 = 1;
mem->var_Int.pe2_100 = 1;
mem->var_Int.pe2_101 = 1;
mem->var_Int.pe2_102 = 1;
mem->var_Int.pe2_103 = 1;
mem->var_Int.pe2_104 = 1;
mem->var_Int.pe2_105 = 1;
mem->var_Int.pe2_106 = 1;
mem->var_Int.pe2_107 = 1;
mem->var_Int.pe2_108 = 1;
mem->var_Int.pe2_109 = 1;
mem->var_Int.pe2_110 = 1;
mem->var_Int.pe2_111 = 1;
mem->var_Int.pe2_112 = 1;
mem->var_Int.pe2_113 = 1;
mem->var_Int.pe2_114 = 1;
mem->var_Int.pe2_115 = 1;
mem->var_Int.pe2_116 = 1;
mem->var_Int.pe2_117 = 1;
mem->var_Int.pe2_118 = 1;
mem->var_Int.pe2_119 = 1;
mem->var_Int.pe2_120 = 1;
mem->var_Int.pe2_121 = 1;
mem->var_Int.pe2_122 = 1;
mem->var_Int.pe2_123 = 1;
mem->var_Int.pe2_124 = 1;
mem->var_Int.pe2_125 = 1;
mem->var_Int.pe2_126 = 1;
mem->var_Int.pe2_127 = 1;
mem->var_Int.pe2_128 = 1;
mem->var_Int.pe2_129 = 1;
mem->var_Int.pe2_130 = 1;
mem->var_Int.pe2_131 = 1;
mem->var_Int.pe2_132 = 1;
mem->var_Int.pe2_133 = 1;
mem->var_Int.pe2_134 = 1;
mem->var_Int.pe2_135 = 1;
mem->var_Int.pe2_136 = 1;
mem->var_Int.pe2_137 = 1;
mem->var_Int.pe2_138 = 1;
mem->var_Int.pe2_139 = 1;
mem->var_Int.pe2_140 = 1;
mem->var_Int.pe2_141 = 1;
mem->var_Int.pe2_142 = 1;
mem->var_Int.pe2_143 = 1;
mem->var_Int.pe2_144 = 1;
mem->var_float.R1_humidity = 0;
mem->var_float.R1_temp = 0;
mem->var_float.R1_L_humidity = 0;
mem->var_float.R1_L_temp = 0;
mem->var_float.R2_humidity = 0;
mem->var_float.R2_temp = 0;
mem->var_float.R2_L_humidity = 0;
mem->var_float.R2_L_temp = 0;
mem->var_float.R3_humidity = 0;
mem->var_float.R3_temp = 0;
mem->var_float.R3_L_humidity = 0;
mem->var_float.R3_L_temp = 0;
mem->var_float.R4_humidity = 0;
mem->var_float.R4_temp = 0;
mem->var_float.R4_L_humidity = 0;
mem->var_float.R4_L_temp = 0;
mem->var_float.R5_humidity = 0;
mem->var_float.R5_temp = 0;
mem->var_float.R5_L_humidity = 0;
mem->var_float.R5_L_temp = 0;
mem->var_float.R6_humidity = 0;
mem->var_float.R6_temp = 0;
mem->var_float.R6_L_humidity = 0;
mem->var_float.R6_L_temp = 0;
mem->var_float.R7_humidity = 0;
mem->var_float.R7_temp = 0;
mem->var_float.R7_L_humidity = 0;
mem->var_float.R7_L_temp = 0;
mem->var_float.R8_humidity = 0;
mem->var_float.R8_temp = 0;
mem->var_float.R8_L_humidity = 0;
mem->var_float.R8_L_temp = 0;
mem->var_float.R9_humidity = 0;
mem->var_float.R9_temp = 0;
mem->var_float.R9_L_humidity = 0;
mem->var_float.R9_L_temp = 0;
mem->var_float.R10_humidity = 0;
mem->var_float.R10_temp = 0;
mem->var_float.R10_L_humidity = 0;
mem->var_float.R10_L_temp = 0;
mem->var_float.R11_humidity = 0;
mem->var_float.R11_temp = 0;
mem->var_float.R11_L_humidity = 0;
mem->var_float.R11_L_temp = 0;
mem->var_float.R12_humidity = 0;
mem->var_float.R12_temp = 0;
mem->var_float.R12_L_humidity = 0;
mem->var_float.R12_L_temp = 0;
mem->var_float.R13_humidity = 0;
mem->var_float.R13_temp = 0;
mem->var_float.R13_L_humidity = 0;
mem->var_float.R13_L_temp = 0;
mem->var_float.R14_humidity = 0;
mem->var_float.R14_temp = 0;
mem->var_float.R14_L_humidity = 0;
mem->var_float.R14_L_temp = 0;
mem->var_float.R15_humidity = 0;
mem->var_float.R15_temp = 0;
mem->var_float.R15_L_humidity = 0;
mem->var_float.R15_L_temp = 0;
mem->var_float.R16_humidity = 0;
mem->var_float.R16_temp = 0;
mem->var_float.R16_L_humidity = 0;
mem->var_float.R16_L_temp = 0;
mem->var_float.R17_humidity = 0;
mem->var_float.R17_temp = 0;
mem->var_float.R17_L_humidity = 0;
mem->var_float.R17_L_temp = 0;
mem->var_float.R18_humidity = 0;
mem->var_float.R18_temp = 0;
mem->var_float.R18_L_humidity = 0;
mem->var_float.R18_L_temp = 0;
mem->var_float.R19_humidity = 0;
mem->var_float.R19_temp = 0;
mem->var_float.R19_L_humidity = 0;
mem->var_float.R19_L_temp = 0;
mem->var_float.R20_humidity = 0;
mem->var_float.R20_temp = 0;
mem->var_float.R20_L_humidity = 0;
mem->var_float.R20_L_temp = 0;
mem->var_float.R21_humidity = 0;
mem->var_float.R21_temp = 0;
mem->var_float.R21_L_humidity = 0;
mem->var_float.R21_L_temp = 0;
mem->var_float.R22_humidity = 0;
mem->var_float.R22_temp = 0;
mem->var_float.R22_L_humidity = 0;
mem->var_float.R22_L_temp = 0;
mem->var_float.R23_humidity = 0;
mem->var_float.R23_temp = 0;
mem->var_float.R23_L_humidity = 0;
mem->var_float.R23_L_temp = 0;
mem->var_float.R24_humidity = 0;
mem->var_float.R24_temp = 0;
mem->var_float.R24_L_humidity = 0;
mem->var_float.R24_L_temp = 0;
mem->var_Int.pe2_145 = 1;
mem->var_Word.R1_ec1 = 0;
mem->var_float.R1_salt1 = 0;
mem->var_Int.pe2_146 = 1;
mem->var_Int.kalibre1 = 0;
mem->var_Word.kal = 0;
mem->var_float.kal1 = 0;
mem->var_Word.ortlama_1_9 = 0;
mem->var_Word.ortlama_1_9_20 = 0;
mem->var_Word.son_ortlama_1_9_20 = 0;
mem->var_Word.ortlama_3_9_17 = 0;
mem->var_Word.son_ortlama_3_9_17 = 0;
mem->var_Word.ortlama_1_9_17 = 0;
mem->var_Word.son_ortlama_1_9_17 = 0;
mem->var_Word.ortlama_2_10 = 0;
mem->var_Word.ortlama_2_10_18 = 0;
mem->var_Word.son_ortlama_2_10_18 = 0;
mem->var_Word.ortlama_3_11 = 0;
mem->var_Word.ortlama_3_11_19 = 0;
mem->var_Word.son_ortlama_3_11_19 = 0;
mem->var_Word.son_ortlama_3 = 0;
mem->var_Word.ortlama_4_12 = 0;
mem->var_Word.ortlama_4_12_20 = 0;
mem->var_Word.son_ortlama_4_12_20 = 0;
mem->var_Word.ortlama_5_13 = 0;
mem->var_Word.ortlama_5_13_21 = 0;
mem->var_Word.son_ortlama_5_13_20 = 0;
mem->var_Word.son_ortlama_5_13_21 = 0;
mem->var_Word.ortlama_6_14 = 0;
mem->var_Word.ortlama_6_14_22 = 0;
mem->var_Word.son_ortlama_6_14_22 = 0;
mem->var_Word.R115_humidity = 0;
mem->var_Word.ortlama_7_15 = 0;
mem->var_Word.ortlama_7_15_23 = 0;
mem->var_Word.son_ortlama_7_15_23 = 0;
mem->var_Word.ortlama_8_16 = 0;
mem->var_Word.ortlama_8_16_24 = 0;
mem->var_Word.son_ortlama_8_16_24 = 0;
mem->var_Word.Exp01_InpWord_01 = 0;
mem->var_Word.Exp01_OutWord_01 = 0;
mem->var_Word.Exp01_OutWordHlp_01 = 0;
mem->var_Int.Exp02_Sen0_Val_02 = 0;
mem->var_Int.Exp02_Sen0_Filter_02 = 1;
mem->var_Int.Exp02_Sen0_Satus_02 = 0;
mem->var_Int.Exp02_Sen1_Val_02 = 0;
mem->var_Int.Exp02_Sen1_Filter_02 = 1;
mem->var_Int.Exp02_Sen1_Satus_02 = 0;
mem->var_Int.Exp02_Sen2_Val_02 = 0;
mem->var_Int.Exp02_Sen2_Filter_02 = 1;
mem->var_Int.Exp02_Sen2_Satus_02 = 0;
mem->var_Int.Exp02_Sen3_Val_02 = 0;
mem->var_Int.Exp02_Sen3_Filter_02 = 1;
mem->var_Int.Exp02_Sen3_Satus_02 = 0;
mem->gmtfn1 = 0;
mem->gmtfn10 = 0;
mem->gmtfn100 = 0;
mem->gmtfn103 = 0;
mem->gmtfn104 = 0;
mem->gmtfn105 = 0;
mem->gmtfn108 = 0;
mem->gmtfn109 = 0;
mem->gmtfn110 = 0;
mem->gmtfn113 = 0;
mem->gmtfn114 = 0;
mem->gmtfn115 = 0;
mem->gmtfn118 = 0;
mem->gmtfn119 = 0;
mem->gmtfn120 = 0;
mem->gmtfn123 = 0;
mem->gmtfn124 = 0;
mem->gmtfn125 = 0;
mem->gmtfn13 = 0;
mem->gmtfn132 = 0;
mem->gmtfn133 = 0;
mem->gmtfn134 = 0;
mem->gmtfn14 = 0;
mem->gmtfn141 = 0;
mem->gmtfn142 = 0;
mem->gmtfn143 = 0;
mem->gmtfn15 = 0;
mem->gmtfn150 = 0;
mem->gmtfn151 = 0;
mem->gmtfn152 = 0;
mem->gmtfn159 = 0;
mem->gmtfn160 = 0;
mem->gmtfn161 = 0;
mem->gmtfn168 = 0;
mem->gmtfn169 = 0;
mem->gmtfn170 = 0;
mem->gmtfn177 = 0;
mem->gmtfn178 = 0;
mem->gmtfn179 = 0;
mem->gmtfn18 = 0;
mem->gmtfn186 = 0;
mem->gmtfn187 = 0;
mem->gmtfn188 = 0;
mem->gmtfn19 = 0;
mem->gmtfn2 = 0;
mem->gmtfn20 = 0;
mem->gmtfn23 = 0;
mem->gmtfn24 = 0;
mem->gmtfn25 = 0;
mem->gmtfn28 = 0;
mem->gmtfn29 = 0;
mem->gmtfn3 = 0;
mem->gmtfn30 = 0;
mem->gmtfn33 = 0;
mem->gmtfn34 = 0;
mem->gmtfn35 = 0;
mem->gmtfn38 = 0;
mem->gmtfn39 = 0;
mem->gmtfn4 = 0;
mem->gmtfn40 = 0;
mem->gmtfn43 = 0;
mem->gmtfn44 = 0;
mem->gmtfn45 = 0;
mem->gmtfn48 = 0;
mem->gmtfn49 = 0;
mem->gmtfn5 = 0;
mem->gmtfn50 = 0;
mem->gmtfn53 = 0;
mem->gmtfn54 = 0;
mem->gmtfn55 = 0;
mem->gmtfn58 = 0;
mem->gmtfn59 = 0;
mem->gmtfn60 = 0;
mem->gmtfn63 = 0;
mem->gmtfn64 = 0;
mem->gmtfn65 = 0;
mem->gmtfn68 = 0;
mem->gmtfn69 = 0;
mem->gmtfn7 = 0;
mem->gmtfn70 = 0;
mem->gmtfn73 = 0;
mem->gmtfn74 = 0;
mem->gmtfn75 = 0;
mem->gmtfn78 = 0;
mem->gmtfn79 = 0;
mem->gmtfn8 = 0;
mem->gmtfn80 = 0;
mem->gmtfn83 = 0;
mem->gmtfn84 = 0;
mem->gmtfn85 = 0;
mem->gmtfn88 = 0;
mem->gmtfn89 = 0;
mem->gmtfn9 = 0;
mem->gmtfn90 = 0;
mem->gmtfn93 = 0;
mem->gmtfn94 = 0;
mem->gmtfn95 = 0;
mem->gmtfn98 = 0;
mem->gmtfn99 = 0;
}
void cl_fReadFromFlash()
{
mem_flash[0] = MEM_GETADDR(var_Int.CPU_HSC0_Cnt);
mem_flash[1] = MEM_GETADDR(var_Int.CPU_HSC1_Cnt);
mem_flash[2] = MEM_GETADDR(var_Int.CPU_HSC2_Cnt);
mem_flash[3] = MEM_GETADDR(var_bit.vana1);
mem_flash[4] = MEM_GETADDR(var_bit.vana2);
mem_flash[5] = MEM_GETADDR(var_bit.vana3);
mem_flash[6] = MEM_GETADDR(var_bit.vana4);
mem_flash[7] = MEM_GETADDR(var_bit.vana5);
mem_flash[8] = MEM_GETADDR(var_bit.vana7);
mem_flash[9] = MEM_GETADDR(var_bit.vana6);
mem_flash[10] = MEM_GETADDR(var_bit.vana8);
for (int prsayac = 11; prsayac < 1023; prsayac++) {
  mem_flash[prsayac] = (U32)&flash_dummy_degisken;}
}
void cl_fPIDCompile(void)
 {
 #ifdef PLC_SIM
 plcvar_t *mem = plcvar;
 #else
 plcvar_t *mem = &plcvar;
 #endif //PLC_SIM
I32 params[16];
  }
void cl_fModulinit(void)
 {
 #ifdef PLC_SIM
 plcvar_t *mem = plcvar;
 #else
 plcvar_t *mem = &plcvar;
 #endif //PLC_SIM
I32 params[16];
#if IMG_REVISION >= 515
if (net!=DRIVER_NET)net = DRV_OPEN(DRIVER_NET, 0);
#endif
mem->QP[0]=0;
mem->QP[1]=0;
mem->QP[2]=0;
mem->QP[3]=0;
mem->QP[4]=0;
mem->QP[5]=0;
SI[14]=502;
SI[15]=1000;
if (com != DRIVER_COM)
if ((com = DRV_OPEN(DRIVER_COM, 0)) != DRIVER_INVALID)
{
U32 dev_addr, dev_size;
U32 tag_addr, tag_size;
get_devtag_info(&dev_addr, &dev_size, &tag_addr, &tag_size);
params[0] = APP_GET_VRADDR(dev_addr);
params[1] = dev_size;
params[2] = APP_GET_VRADDR(tag_addr);
params[3] = tag_size;
DRV_IOCTL(com, IOCTL_COM_MBMASTERINIT, params);
params[0] = 1;
params[1] = 1;
params[2] = 9600;
params[3] = 0;
params[4] = 8;
params[5] = 1;
DRV_IOCTL(com, IOCTL_COM_MBSLAVEINIT, params);
}
}
 #ifndef PLC_SIM
static const U32 ModuleMap[]={
EXM_TYPE_EXM88R,	24,
IP_Addr(16),IP_Addr(17),IP_Addr(18),IP_Addr(19),IP_Addr(20),IP_Addr(21),IP_Addr(22),IP_Addr(23),
QP_Addr(16),QP_Addr(17),QP_Addr(18),QP_Addr(19),QP_Addr(20),QP_Addr(21),QP_Addr(22),QP_Addr(23),
IPFil_Addr(16),IPFil_Addr(17),IPFil_Addr(18),IPFil_Addr(19),IPFil_Addr(20),IPFil_Addr(21),IPFil_Addr(22),IPFil_Addr(23),
EXM_TYPE_EXM40U,	72,
CVal(SEN_INVALID),CVal(SEN_INVALID),CVal(SEN_INVALID),CVal(SEN_INVALID),
CVal(0),CVal(0),CVal(0),CVal(0),
CVal(0),CVal(0),CVal(0),CVal(0),
CVal(0),CVal(0),CVal(0),CVal(0),
CVal(0),            CVal(0),            CVal(0),            CVal(0),        // CH0
CVal(0),            CVal(0),            CVal(0),            CVal(0),        // CH0
CVal(0),            CVal(0),            CVal(0),            CVal(0),        // CH0
CVal(0),            CVal(0),            CVal(0),            CVal(0),        // CH0
//Temperatures
DMY_Addr(),DMY_Addr(),DMY_Addr(),DMY_Addr(),
//Alarms
DMY_Addr(),DMY_Addr(),DMY_Addr(),DMY_Addr(),
CVal(0),CVal(0),CVal(0),CVal(0),
DMY_Addr(),            DMY_Addr(),            DMY_Addr(),            DMY_Addr(),
DMY_Addr(),            DMY_Addr(),            DMY_Addr(),            DMY_Addr(),
DMY_Addr(),            DMY_Addr(),            DMY_Addr(),            DMY_Addr(),
DMY_Addr(),            DMY_Addr(),            DMY_Addr(),            DMY_Addr(),
DMY_Addr(),DMY_Addr(),DMY_Addr(),DMY_Addr(),
DMY_Addr(),DMY_Addr(),DMY_Addr(),DMY_Addr(),
DMY_Addr(),DMY_Addr(),DMY_Addr(),DMY_Addr(),
0};
#endif //PLC_SIM
void get_module_info(U32 *addr, U32 *size)
{
#ifndef PLC_SIM
    *addr = (U32)ModuleMap;
    *size = (sizeof(ModuleMap)/sizeof(ModuleMap[0]))-1;
#endif //PLC_SIM
}//get_module_info
#define gmt_HSO0anlik  dummy_data
#define gmt_HSO1anlik  dummy_data
#define gmt_HSO2anlik  dummy_data
struct{
U8 stat[MBPROC_MAX_DEVCNT];
} var_DEV;
struct{
U8 stat[MBPROC_MAX_TAGCNT];
} var_TAG;
 #ifndef PLC_SIM
static const mbdev_t dev_table[]={
{COM_MED_RS485,{0,0,8,1,4800},{ IPADDR(169,254,89,148), 502 },300,0,MB_DATA_LE,(I32)&(plcvar.var_Int.CPU_COM2_Status)}
};
static const mbtag_t tag_table[]={
{0,1,MBPROC_TYP_READ,40001,(I32)&(plcvar.var_Word.R1_humidity1),1,(I32)&(plcvar.var_Int.ps2_0)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_0)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,1,MBPROC_TYP_READ,40002,(I32)&(plcvar.var_Word.R1_temp1),1,(I32)&(plcvar.var_Int.ps2_1)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_1)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,1,MBPROC_TYP_READ,40003,(I32)&(plcvar.var_Word.R1_ec),1,(I32)&(plcvar.var_Int.ps2_2)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_2)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,1,MBPROC_TYP_READ,40004,(I32)&(plcvar.var_Word.R1_salt),1,(I32)&(plcvar.var_Int.ps2_3)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_3)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,2,MBPROC_TYP_READ,40001,(I32)&(plcvar.var_Word.R2_humidity2),1,(I32)&(plcvar.var_Int.ps2_5)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_5)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,2,MBPROC_TYP_READ,40002,(I32)&(plcvar.var_Word.R2_temp2),1,(I32)&(plcvar.var_Int.ps2_6)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_6)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,2,MBPROC_TYP_READ,40003,(I32)&(plcvar.var_Word.R2_ec),1,(I32)&(plcvar.var_Int.ps2_7)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_7)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,2,MBPROC_TYP_READ,40004,(I32)&(plcvar.var_Word.R2_salt),1,(I32)&(plcvar.var_Int.ps2_8)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_8)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,3,MBPROC_TYP_READ,40001,(I32)&(plcvar.var_Word.R3_humidity3),1,(I32)&(plcvar.var_Int.ps2_9)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_9)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,3,MBPROC_TYP_READ,40002,(I32)&(plcvar.var_Word.R3_temp3),1,(I32)&(plcvar.var_Int.ps2_10)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_10)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,3,MBPROC_TYP_READ,40003,(I32)&(plcvar.var_Word.R3_ec),1,(I32)&(plcvar.var_Int.ps2_11)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_11)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,3,MBPROC_TYP_READ,40004,(I32)&(plcvar.var_Word.R3_salt),1,(I32)&(plcvar.var_Int.ps2_12)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_12)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,4,MBPROC_TYP_READ,40001,(I32)&(plcvar.var_Word.R4_humidity4),1,(I32)&(plcvar.var_Int.ps2_13)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_13)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,4,MBPROC_TYP_READ,40002,(I32)&(plcvar.var_Word.R4_temp4),1,(I32)&(plcvar.var_Int.ps2_14)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_14)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,4,MBPROC_TYP_READ,40003,(I32)&(plcvar.var_Word.R4_ec),1,(I32)&(plcvar.var_Int.ps2_15)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_15)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,4,MBPROC_TYP_READ,40004,(I32)&(plcvar.var_Word.R4_salt),1,(I32)&(plcvar.var_Int.ps2_16)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_16)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,5,MBPROC_TYP_READ,40001,(I32)&(plcvar.var_Word.R5_humidity5),1,(I32)&(plcvar.var_Int.ps2_17)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_17)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,5,MBPROC_TYP_READ,40002,(I32)&(plcvar.var_Word.R5_temp5),1,(I32)&(plcvar.var_Int.ps2_18)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_18)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,5,MBPROC_TYP_READ,40003,(I32)&(plcvar.var_Word.R5_ec),1,(I32)&(plcvar.var_Int.ps2_19)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_19)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,5,MBPROC_TYP_READ,40004,(I32)&(plcvar.var_Word.R5_salt),1,(I32)&(plcvar.var_Int.ps2_20)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_20)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,6,MBPROC_TYP_READ,40001,(I32)&(plcvar.var_Word.R6_humidity6),1,(I32)&(plcvar.var_Int.ps2_21)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_21)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,6,MBPROC_TYP_READ,40002,(I32)&(plcvar.var_Word.R6_temp6),1,(I32)&(plcvar.var_Int.ps2_22)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_22)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,6,MBPROC_TYP_READ,40003,(I32)&(plcvar.var_Word.R6_ec),1,(I32)&(plcvar.var_Int.ps2_23)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_23)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,6,MBPROC_TYP_READ,40004,(I32)&(plcvar.var_Word.R6_salt),1,(I32)&(plcvar.var_Int.ps2_24)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_24)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,7,MBPROC_TYP_READ,40001,(I32)&(plcvar.var_Word.R7_humidity7),1,(I32)&(plcvar.var_Int.ps2_25)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_25)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,7,MBPROC_TYP_READ,40002,(I32)&(plcvar.var_Word.R7_temp7),1,(I32)&(plcvar.var_Int.ps2_26)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_26)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,7,MBPROC_TYP_READ,40003,(I32)&(plcvar.var_Word.R7_ec),1,(I32)&(plcvar.var_Int.ps2_27)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_27)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,7,MBPROC_TYP_READ,40004,(I32)&(plcvar.var_Word.R7_salt),1,(I32)&(plcvar.var_Int.ps2_28)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_28)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,8,MBPROC_TYP_READ,40001,(I32)&(plcvar.var_Word.R8_humidity8),1,(I32)&(plcvar.var_Int.ps2_29)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_29)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,8,MBPROC_TYP_READ,40002,(I32)&(plcvar.var_Word.R8_temp8),1,(I32)&(plcvar.var_Int.ps2_30)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_30)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,8,MBPROC_TYP_READ,40003,(I32)&(plcvar.var_Word.R8_ec),1,(I32)&(plcvar.var_Int.ps2_31)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_31)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,8,MBPROC_TYP_READ,40004,(I32)&(plcvar.var_Word.R8_salt),1,(I32)&(plcvar.var_Int.ps2_32)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_32)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,9,MBPROC_TYP_READ,40001,(I32)&(plcvar.var_Word.R9_humidity9),1,(I32)&(plcvar.var_Int.ps2_33)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_33)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,9,MBPROC_TYP_READ,40002,(I32)&(plcvar.var_Word.R9_temp9),1,(I32)&(plcvar.var_Int.ps2_34)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_34)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,9,MBPROC_TYP_READ,40003,(I32)&(plcvar.var_Word.R9_ec),1,(I32)&(plcvar.var_Int.ps2_35)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_35)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,9,MBPROC_TYP_READ,40004,(I32)&(plcvar.var_Word.R9_salt),1,(I32)&(plcvar.var_Int.ps2_36)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_36)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,10,MBPROC_TYP_READ,40001,(I32)&(plcvar.var_Word.R10_humidity10),1,(I32)&(plcvar.var_Int.ps2_37)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_37)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,10,MBPROC_TYP_READ,40002,(I32)&(plcvar.var_Word.R10_temp10),1,(I32)&(plcvar.var_Int.ps2_38)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_38)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,10,MBPROC_TYP_READ,40003,(I32)&(plcvar.var_Word.R10_ec),1,(I32)&(plcvar.var_Int.ps2_39)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_39)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,10,MBPROC_TYP_READ,40004,(I32)&(plcvar.var_Word.R10_salt),1,(I32)&(plcvar.var_Int.ps2_40)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_40)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,11,MBPROC_TYP_READ,40001,(I32)&(plcvar.var_Word.R11_humidity11),1,(I32)&(plcvar.var_Int.ps2_41)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_41)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,11,MBPROC_TYP_READ,40002,(I32)&(plcvar.var_Word.R11_temp11),1,(I32)&(plcvar.var_Int.ps2_42)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_42)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,11,MBPROC_TYP_READ,40003,(I32)&(plcvar.var_Word.R11_ec),1,(I32)&(plcvar.var_Int.ps2_43)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_43)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,11,MBPROC_TYP_READ,40004,(I32)&(plcvar.var_Word.R11_salt),1,(I32)&(plcvar.var_Int.ps2_44)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_44)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,12,MBPROC_TYP_READ,40001,(I32)&(plcvar.var_Word.R12_humidity12),1,(I32)&(plcvar.var_Int.ps2_45)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_45)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,12,MBPROC_TYP_READ,40002,(I32)&(plcvar.var_Word.R12_temp12),1,(I32)&(plcvar.var_Int.ps2_46)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_46)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,12,MBPROC_TYP_READ,40003,(I32)&(plcvar.var_Word.R12_ec),1,(I32)&(plcvar.var_Int.ps2_47)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_47)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,12,MBPROC_TYP_READ,40004,(I32)&(plcvar.var_Word.R12_salt),1,(I32)&(plcvar.var_Int.ps2_48)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_48)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,13,MBPROC_TYP_READ,40001,(I32)&(plcvar.var_Word.R13_humidity13),1,(I32)&(plcvar.var_Int.ps2_49)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_49)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,13,MBPROC_TYP_READ,40002,(I32)&(plcvar.var_Word.R13_temp13),1,(I32)&(plcvar.var_Int.ps2_50)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_50)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,13,MBPROC_TYP_READ,40003,(I32)&(plcvar.var_Word.R13_ec),1,(I32)&(plcvar.var_Int.ps2_51)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_51)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,13,MBPROC_TYP_READ,40004,(I32)&(plcvar.var_Word.R13_salt),1,(I32)&(plcvar.var_Int.ps2_52)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_52)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,14,MBPROC_TYP_READ,40001,(I32)&(plcvar.var_Word.R14_humidity14),1,(I32)&(plcvar.var_Int.ps2_53)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_53)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,14,MBPROC_TYP_READ,40002,(I32)&(plcvar.var_Word.R14_temp14),1,(I32)&(plcvar.var_Int.ps2_54)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_54)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,14,MBPROC_TYP_READ,40003,(I32)&(plcvar.var_Word.R14_ec),1,(I32)&(plcvar.var_Int.ps2_55)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_55)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,14,MBPROC_TYP_READ,40004,(I32)&(plcvar.var_Word.R14_salt),1,(I32)&(plcvar.var_Int.ps2_56)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_56)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,15,MBPROC_TYP_READ,40001,(I32)&(plcvar.var_Word.R15_humidity15),1,(I32)&(plcvar.var_Int.ps2_57)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_57)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,15,MBPROC_TYP_READ,40002,(I32)&(plcvar.var_Word.R15_temp15),1,(I32)&(plcvar.var_Int.ps2_58)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_58)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,15,MBPROC_TYP_READ,40003,(I32)&(plcvar.var_Word.R15_ec),1,(I32)&(plcvar.var_Int.ps2_59)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_59)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,15,MBPROC_TYP_READ,40004,(I32)&(plcvar.var_Word.R15_salt),1,(I32)&(plcvar.var_Int.ps2_60)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_60)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,16,MBPROC_TYP_READ,40001,(I32)&(plcvar.var_Word.R16_humidity16),1,(I32)&(plcvar.var_Int.ps2_61)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_61)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,16,MBPROC_TYP_READ,40002,(I32)&(plcvar.var_Word.R16_temp16),1,(I32)&(plcvar.var_Int.ps2_62)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_62)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,16,MBPROC_TYP_READ,40003,(I32)&(plcvar.var_Word.R16_ec),1,(I32)&(plcvar.var_Int.ps2_63)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_63)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,16,MBPROC_TYP_READ,40004,(I32)&(plcvar.var_Word.R16_salt),1,(I32)&(plcvar.var_Int.ps2_64)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_64)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,17,MBPROC_TYP_READ,40001,(I32)&(plcvar.var_Word.R17_humidity17),1,(I32)&(plcvar.var_Int.ps2_65)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_65)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,17,MBPROC_TYP_READ,40002,(I32)&(plcvar.var_Word.R17_temp17),1,(I32)&(plcvar.var_Int.ps2_66)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_66)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,17,MBPROC_TYP_READ,40003,(I32)&(plcvar.var_Word.R17_ec),1,(I32)&(plcvar.var_Int.ps2_67)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_67)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,17,MBPROC_TYP_READ,40004,(I32)&(plcvar.var_Word.R17_salt),1,(I32)&(plcvar.var_Int.ps2_68)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_68)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,18,MBPROC_TYP_READ,40001,(I32)&(plcvar.var_Word.R18_humidity18),1,(I32)&(plcvar.var_Int.ps2_69)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_69)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,18,MBPROC_TYP_READ,40002,(I32)&(plcvar.var_Word.R18_temp18),1,(I32)&(plcvar.var_Int.ps2_70)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_70)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,18,MBPROC_TYP_READ,40003,(I32)&(plcvar.var_Word.R18_ec),1,(I32)&(plcvar.var_Int.ps2_71)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_71)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,18,MBPROC_TYP_READ,40004,(I32)&(plcvar.var_Word.R18_salt),1,(I32)&(plcvar.var_Int.ps2_72)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_72)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,19,MBPROC_TYP_READ,40001,(I32)&(plcvar.var_Word.R19_humidity19),1,(I32)&(plcvar.var_Int.ps2_73)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_73)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,19,MBPROC_TYP_READ,40002,(I32)&(plcvar.var_Word.R19_temp19),1,(I32)&(plcvar.var_Int.ps2_74)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_74)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,19,MBPROC_TYP_READ,40003,(I32)&(plcvar.var_Word.R19_ec),1,(I32)&(plcvar.var_Int.ps2_75)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_75)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,19,MBPROC_TYP_READ,40004,(I32)&(plcvar.var_Word.R19_salt),1,(I32)&(plcvar.var_Int.ps2_76)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_76)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,20,MBPROC_TYP_READ,40001,(I32)&(plcvar.var_Word.R20_humidity20),1,(I32)&(plcvar.var_Int.ps2_77)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_77)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,20,MBPROC_TYP_READ,40002,(I32)&(plcvar.var_Word.R20_temp20),1,(I32)&(plcvar.var_Int.ps2_78)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_78)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,20,MBPROC_TYP_READ,40003,(I32)&(plcvar.var_Word.R20_ec),1,(I32)&(plcvar.var_Int.ps2_79)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_79)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,20,MBPROC_TYP_READ,40004,(I32)&(plcvar.var_Word.R20_salt),1,(I32)&(plcvar.var_Int.ps2_80)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_80)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,21,MBPROC_TYP_READ,40001,(I32)&(plcvar.var_Word.R21_humidity21),1,(I32)&(plcvar.var_Int.ps2_81)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_81)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,21,MBPROC_TYP_READ,40002,(I32)&(plcvar.var_Word.R21_temp21),1,(I32)&(plcvar.var_Int.ps2_82)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_82)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,21,MBPROC_TYP_READ,40003,(I32)&(plcvar.var_Word.R21_ec),1,(I32)&(plcvar.var_Int.ps2_83)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_83)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,21,MBPROC_TYP_READ,40004,(I32)&(plcvar.var_Word.R21_salt),1,(I32)&(plcvar.var_Int.ps2_84)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_84)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,22,MBPROC_TYP_READ,40001,(I32)&(plcvar.var_Word.R22_humidity22),1,(I32)&(plcvar.var_Int.ps2_85)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_85)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,22,MBPROC_TYP_READ,40002,(I32)&(plcvar.var_Word.R22_temp22),1,(I32)&(plcvar.var_Int.ps2_86)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_86)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,22,MBPROC_TYP_READ,40003,(I32)&(plcvar.var_Word.R22_ec),1,(I32)&(plcvar.var_Int.ps2_87)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_87)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,22,MBPROC_TYP_READ,40004,(I32)&(plcvar.var_Word.R22_salt),1,(I32)&(plcvar.var_Int.ps2_88)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_88)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,23,MBPROC_TYP_READ,40001,(I32)&(plcvar.var_Word.R23_humidity23),1,(I32)&(plcvar.var_Int.ps2_89)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_89)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,23,MBPROC_TYP_READ,40002,(I32)&(plcvar.var_Word.R23_temp23),1,(I32)&(plcvar.var_Int.ps2_90)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_90)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,23,MBPROC_TYP_READ,40003,(I32)&(plcvar.var_Word.R23_ec),1,(I32)&(plcvar.var_Int.ps2_91)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_91)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,23,MBPROC_TYP_READ,40004,(I32)&(plcvar.var_Word.R23_salt),1,(I32)&(plcvar.var_Int.ps2_92)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_92)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,24,MBPROC_TYP_READ,40001,(I32)&(plcvar.var_Word.R24_humidity24),1,(I32)&(plcvar.var_Int.ps2_93)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_93)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,24,MBPROC_TYP_READ,40002,(I32)&(plcvar.var_Word.R24_temp24),1,(I32)&(plcvar.var_Int.ps2_94)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_94)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,24,MBPROC_TYP_READ,40003,(I32)&(plcvar.var_Word.R24_ec),1,(I32)&(plcvar.var_Int.ps2_95)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_95)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,24,MBPROC_TYP_READ,40004,(I32)&(plcvar.var_Word.R24_salt),1,(I32)&(plcvar.var_Int.ps2_96)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_96)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,101,MBPROC_TYP_READ,40001,(I32)&(plcvar.var_Word.R1_L_humidity101),1,(I32)&(plcvar.var_Int.ps2_97)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_97)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,101,MBPROC_TYP_READ,40002,(I32)&(plcvar.var_Word.R1_L_temp101),1,(I32)&(plcvar.var_Int.ps2_98)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_98)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,102,MBPROC_TYP_READ,40001,(I32)&(plcvar.var_Word.R2_L_humidity102),1,(I32)&(plcvar.var_Int.ps2_99)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_99)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,102,MBPROC_TYP_READ,40002,(I32)&(plcvar.var_Word.R2_L_temp102),1,(I32)&(plcvar.var_Int.ps2_100)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_100)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,103,MBPROC_TYP_READ,40001,(I32)&(plcvar.var_Word.R3_L_humidity103),1,(I32)&(plcvar.var_Int.ps2_101)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_101)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,103,MBPROC_TYP_READ,40002,(I32)&(plcvar.var_Word.R3_L_temp103),1,(I32)&(plcvar.var_Int.ps2_102)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_102)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,104,MBPROC_TYP_READ,40001,(I32)&(plcvar.var_Word.R4_L_humidity104),1,(I32)&(plcvar.var_Int.ps2_103)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_103)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,104,MBPROC_TYP_READ,40002,(I32)&(plcvar.var_Word.R4_L_temp104),1,(I32)&(plcvar.var_Int.ps2_104)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_104)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,105,MBPROC_TYP_READ,40001,(I32)&(plcvar.var_Word.R5_L_humidity105),1,(I32)&(plcvar.var_Int.ps2_105)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_105)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,105,MBPROC_TYP_READ,40002,(I32)&(plcvar.var_Word.R5_L_temp105),1,(I32)&(plcvar.var_Int.ps2_106)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_106)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,106,MBPROC_TYP_READ,40001,(I32)&(plcvar.var_Word.R6_L_humidity106),1,(I32)&(plcvar.var_Int.ps2_107)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_107)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,106,MBPROC_TYP_READ,40002,(I32)&(plcvar.var_Word.R6_L_temp106),1,(I32)&(plcvar.var_Int.ps2_108)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_108)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,107,MBPROC_TYP_READ,40001,(I32)&(plcvar.var_Word.R7_L_humidity107),1,(I32)&(plcvar.var_Int.ps2_109)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_109)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,107,MBPROC_TYP_READ,40002,(I32)&(plcvar.var_Word.R7_L_temp107),1,(I32)&(plcvar.var_Int.ps2_110)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_110)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,108,MBPROC_TYP_READ,40001,(I32)&(plcvar.var_Word.R8_L_humidity108),1,(I32)&(plcvar.var_Int.ps2_111)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_111)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,108,MBPROC_TYP_READ,40002,(I32)&(plcvar.var_Word.R8_L_temp108),1,(I32)&(plcvar.var_Int.ps2_112)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_112)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,109,MBPROC_TYP_READ,40001,(I32)&(plcvar.var_Word.R9_L_humidity109),1,(I32)&(plcvar.var_Int.ps2_113)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_113)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,109,MBPROC_TYP_READ,40002,(I32)&(plcvar.var_Word.R9_L_temp109),1,(I32)&(plcvar.var_Int.ps2_114)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_114)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,110,MBPROC_TYP_READ,40001,(I32)&(plcvar.var_Word.R10_L_humidity110),1,(I32)&(plcvar.var_Int.ps2_115)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_115)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,110,MBPROC_TYP_READ,40002,(I32)&(plcvar.var_Word.R10_L_temp110),1,(I32)&(plcvar.var_Int.ps2_116)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_116)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,111,MBPROC_TYP_READ,40001,(I32)&(plcvar.var_Word.R11_L_humidity111),1,(I32)&(plcvar.var_Int.ps2_117)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_117)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,111,MBPROC_TYP_READ,40002,(I32)&(plcvar.var_Word.R11_L_temp111),1,(I32)&(plcvar.var_Int.ps2_118)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_118)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,112,MBPROC_TYP_READ,40001,(I32)&(plcvar.var_Word.R12_L_humidity112),1,(I32)&(plcvar.var_Int.ps2_119)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_119)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,112,MBPROC_TYP_READ,40002,(I32)&(plcvar.var_Word.R12_L_temp112),1,(I32)&(plcvar.var_Int.ps2_120)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_120)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,113,MBPROC_TYP_READ,40001,(I32)&(plcvar.var_Word.R13_L_humidity113),1,(I32)&(plcvar.var_Int.ps2_121)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_121)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,113,MBPROC_TYP_READ,40002,(I32)&(plcvar.var_Word.R13_L_temp113),1,(I32)&(plcvar.var_Int.ps2_122)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_122)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,114,MBPROC_TYP_READ,40001,(I32)&(plcvar.var_Word.R14_L_humidity114),1,(I32)&(plcvar.var_Int.ps2_123)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_123)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,114,MBPROC_TYP_READ,40002,(I32)&(plcvar.var_Word.R14_L_temp114),1,(I32)&(plcvar.var_Int.ps2_124)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_124)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,115,MBPROC_TYP_READ,40001,(I32)&(plcvar.var_Word.R15_L_humidity115),1,(I32)&(plcvar.var_Int.ps2_125)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_125)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,115,MBPROC_TYP_READ,40002,(I32)&(plcvar.var_Word.R15_L_temp115),1,(I32)&(plcvar.var_Int.ps2_126)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_126)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,116,MBPROC_TYP_READ,40001,(I32)&(plcvar.var_Word.R16_L_humidity116),1,(I32)&(plcvar.var_Int.ps2_127)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_127)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,116,MBPROC_TYP_READ,40002,(I32)&(plcvar.var_Word.R16_L_temp116),1,(I32)&(plcvar.var_Int.ps2_128)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_128)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,117,MBPROC_TYP_READ,40001,(I32)&(plcvar.var_Word.R17_L_humidity117),1,(I32)&(plcvar.var_Int.ps2_129)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_129)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,117,MBPROC_TYP_READ,40002,(I32)&(plcvar.var_Word.R17_L_temp117),1,(I32)&(plcvar.var_Int.ps2_130)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_130)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,118,MBPROC_TYP_READ,40001,(I32)&(plcvar.var_Word.R18_L_humidity118),1,(I32)&(plcvar.var_Int.ps2_131)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_131)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,118,MBPROC_TYP_READ,40002,(I32)&(plcvar.var_Word.R18_L_temp118),1,(I32)&(plcvar.var_Int.ps2_132)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_132)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,119,MBPROC_TYP_READ,40001,(I32)&(plcvar.var_Word.R19_L_humidity119),1,(I32)&(plcvar.var_Int.ps2_133)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_133)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,119,MBPROC_TYP_READ,40002,(I32)&(plcvar.var_Word.R19_L_temp119),1,(I32)&(plcvar.var_Int.ps2_134)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_134)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,120,MBPROC_TYP_READ,40001,(I32)&(plcvar.var_Word.R20_L_humidity120),1,(I32)&(plcvar.var_Int.ps2_135)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_135)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,120,MBPROC_TYP_READ,40002,(I32)&(plcvar.var_Word.R20_L_temp120),1,(I32)&(plcvar.var_Int.ps2_136)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_136)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,121,MBPROC_TYP_READ,40001,(I32)&(plcvar.var_Word.R21_L_humidity121),1,(I32)&(plcvar.var_Int.ps2_137)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_137)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,121,MBPROC_TYP_READ,40002,(I32)&(plcvar.var_Word.R21_L_temp121),1,(I32)&(plcvar.var_Int.ps2_138)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_138)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,122,MBPROC_TYP_READ,40001,(I32)&(plcvar.var_Word.R22_L_humidity122),1,(I32)&(plcvar.var_Int.ps2_139)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_139)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,122,MBPROC_TYP_READ,40002,(I32)&(plcvar.var_Word.R22_L_temp122),1,(I32)&(plcvar.var_Int.ps2_140)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_140)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,123,MBPROC_TYP_READ,40001,(I32)&(plcvar.var_Word.R23_L_humidity123),1,(I32)&(plcvar.var_Int.ps2_141)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_141)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,123,MBPROC_TYP_READ,40002,(I32)&(plcvar.var_Word.R23_L_temp123),1,(I32)&(plcvar.var_Int.ps2_142)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_142)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,124,MBPROC_TYP_READ,40001,(I32)&(plcvar.var_Word.R24_L_humidity124),1,(I32)&(plcvar.var_Int.ps2_143)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_143)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,124,MBPROC_TYP_READ,40002,(I32)&(plcvar.var_Word.R24_L_temp124),1,(I32)&(plcvar.var_Int.ps2_144)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_144)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,1,MBPROC_TYP_READ,4036,(I32)&(plcvar.var_Word.R1_salt_co),1,(I32)&(plcvar.var_Int.ps2_145)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_145)
#endif
#if IMG_REVISION >= 518
,0
#endif
#if IMG_REVISION >= 519
,0
#endif
}
,
{0,1,MBPROC_TYP_READ,4083,(I32)&(plcvar.var_Int.kalibre),2,(I32)&(plcvar.var_Int.ps2_146)
#if IMG_REVISION >= 517
,(I32)&(plcvar.var_Int.pe2_146)
#endif
#if IMG_REVISION >= 518
,2
#endif
#if IMG_REVISION >= 519
,0
#endif
}
};
  #endif 
void get_devtag_info(U32 *dev_addr, U32 *dev_size,U32 *tag_addr, U32 *tag_size){
 #ifdef PLC_SIM
 *dev_addr = 0;
 *dev_size = 0;
 *tag_addr = 0;
 *tag_size = 0;
 #else
 *dev_addr = (U32)dev_table;
 *dev_size = sizeof(dev_table)/sizeof(dev_table[0]);
 *tag_addr = (U32)tag_table;
 *tag_size = sizeof(tag_table)/sizeof(tag_table[0]);
 #endif //PLC_SIM
 }
 
void cl_f1ms(void)
{
#ifdef PLC_SIM
plcvar_t *mem = plcvar;
#else
plcvar_t *mem = &plcvar;
#endif //PLC_SIM

















































































































































































































}
 
void fn1(void)
 {
 #ifdef PLC_SIM
 plcvar_t *mem = plcvar;
 #else
 plcvar_t *mem = &plcvar;
 #endif //PLC_SIM
 if (mem->gmtfn1) return;
mem->gmtfn1=1;
  if ((10)==0) return; mem->var_float.R1_humidity=(float)(mem->var_Word.R1_humidity1)/((10)); 
 }
void fn2(void)
 {
 #ifdef PLC_SIM
 plcvar_t *mem = plcvar;
 #else
 plcvar_t *mem = &plcvar;
 #endif //PLC_SIM
 if (mem->gmtfn2) return;
mem->gmtfn2=1;
  if ((10)==0) return; mem->var_float.R1_temp=(float)(mem->var_Word.R1_temp1)/((10)); 
 }
void fn3(void)
 {
 #ifdef PLC_SIM
 plcvar_t *mem = plcvar;
 #else
 plcvar_t *mem = &plcvar;
 #endif //PLC_SIM
 if (mem->gmtfn3) return;
mem->gmtfn3=1;
  if ((10)==0) return; mem->var_float.R1_L_humidity=(float)(mem->var_Word.R1_L_humidity101)/((10)); 
 }
void fn4(void)
 {
 #ifdef PLC_SIM
 plcvar_t *mem = plcvar;
 #else
 plcvar_t *mem = &plcvar;
 #endif //PLC_SIM
 if (mem->gmtfn4) return;
mem->gmtfn4=1;
 mem->var_Word.R1_ec1=(mem->var_Word.R1_ec)*((10)); 
 }
void fn5(void)
 {
 #ifdef PLC_SIM
 plcvar_t *mem = plcvar;
 #else
 plcvar_t *mem = &plcvar;
 #endif //PLC_SIM
 if (mem->gmtfn5) return;
mem->gmtfn5=1;
  if ((10)==0) return; mem->var_float.R1_salt1=(float)(mem->var_Word.R1_salt)/((10)); 
 }
void fn7(void)
 {
 #ifdef PLC_SIM
 plcvar_t *mem = plcvar;
 #else
 plcvar_t *mem = &plcvar;
 #endif //PLC_SIM
 if (mem->gmtfn7) return;
mem->gmtfn7=1;
 float linm = 0; if ((((0))-((7))) != 0){     linm = (( (float)( (0) )-( (12) )) / (((0))-((7))));} float linc = ((0) - (0) * linm); 
if ( 0 ){
mem->var_float.kal1 = roundNumber(linm * mem->var_float.R1_salt1 + linc);}
else{
mem->var_float.kal1 =(linm * mem->var_float.R1_salt1 + linc);}
 }
void fn8(void)
 {
 #ifdef PLC_SIM
 plcvar_t *mem = plcvar;
 #else
 plcvar_t *mem = &plcvar;
 #endif //PLC_SIM
 if (mem->gmtfn8) return;
mem->gmtfn8=1;
  if ((10)==0) return; mem->var_float.R2_humidity=(float)(mem->var_Word.R2_humidity2)/((10)); 
 }
void fn9(void)
 {
 #ifdef PLC_SIM
 plcvar_t *mem = plcvar;
 #else
 plcvar_t *mem = &plcvar;
 #endif //PLC_SIM
 if (mem->gmtfn9) return;
mem->gmtfn9=1;
  if ((10)==0) return; mem->var_float.R2_temp=(float)(mem->var_Word.R2_temp2)/((10)); 
 }
void fn10(void)
 {
 #ifdef PLC_SIM
 plcvar_t *mem = plcvar;
 #else
 plcvar_t *mem = &plcvar;
 #endif //PLC_SIM
 if (mem->gmtfn10) return;
mem->gmtfn10=1;
  if ((10)==0) return; mem->var_float.R2_L_humidity=(float)(mem->var_Word.R2_L_humidity102)/((10)); 
 }
void fn13(void)
 {
 #ifdef PLC_SIM
 plcvar_t *mem = plcvar;
 #else
 plcvar_t *mem = &plcvar;
 #endif //PLC_SIM
 if (mem->gmtfn13) return;
mem->gmtfn13=1;
  if ((10)==0) return; mem->var_float.R3_humidity=(float)(mem->var_Word.R3_humidity3)/((10)); 
 }
void fn14(void)
 {
 #ifdef PLC_SIM
 plcvar_t *mem = plcvar;
 #else
 plcvar_t *mem = &plcvar;
 #endif //PLC_SIM
 if (mem->gmtfn14) return;
mem->gmtfn14=1;
  if ((10)==0) return; mem->var_float.R3_temp=(float)(mem->var_Word.R3_temp3)/((10)); 
 }
void fn15(void)
 {
 #ifdef PLC_SIM
 plcvar_t *mem = plcvar;
 #else
 plcvar_t *mem = &plcvar;
 #endif //PLC_SIM
 if (mem->gmtfn15) return;
mem->gmtfn15=1;
  if ((10)==0) return; mem->var_float.R3_L_humidity=(float)(mem->var_Word.R3_L_humidity103)/((10)); 
 }
void fn18(void)
 {
 #ifdef PLC_SIM
 plcvar_t *mem = plcvar;
 #else
 plcvar_t *mem = &plcvar;
 #endif //PLC_SIM
 if (mem->gmtfn18) return;
mem->gmtfn18=1;
  if ((10)==0) return; mem->var_float.R4_humidity=(float)(mem->var_Word.R4_humidity4)/((10)); 
 }
void fn19(void)
 {
 #ifdef PLC_SIM
 plcvar_t *mem = plcvar;
 #else
 plcvar_t *mem = &plcvar;
 #endif //PLC_SIM
 if (mem->gmtfn19) return;
mem->gmtfn19=1;
  if ((10)==0) return; mem->var_float.R4_temp=(float)(mem->var_Word.R4_temp4)/((10)); 
 }
void fn20(void)
 {
 #ifdef PLC_SIM
 plcvar_t *mem = plcvar;
 #else
 plcvar_t *mem = &plcvar;
 #endif //PLC_SIM
 if (mem->gmtfn20) return;
mem->gmtfn20=1;
  if ((10)==0) return; mem->var_float.R4_L_humidity=(float)(mem->var_Word.R4_L_humidity104)/((10)); 
 }
void fn23(void)
 {
 #ifdef PLC_SIM
 plcvar_t *mem = plcvar;
 #else
 plcvar_t *mem = &plcvar;
 #endif //PLC_SIM
 if (mem->gmtfn23) return;
mem->gmtfn23=1;
  if ((10)==0) return; mem->var_float.R5_humidity=(float)(mem->var_Word.R5_humidity5)/((10)); 
 }
void fn24(void)
 {
 #ifdef PLC_SIM
 plcvar_t *mem = plcvar;
 #else
 plcvar_t *mem = &plcvar;
 #endif //PLC_SIM
 if (mem->gmtfn24) return;
mem->gmtfn24=1;
  if ((10)==0) return; mem->var_float.R5_temp=(float)(mem->var_Word.R5_temp5)/((10)); 
 }
void fn25(void)
 {
 #ifdef PLC_SIM
 plcvar_t *mem = plcvar;
 #else
 plcvar_t *mem = &plcvar;
 #endif //PLC_SIM
 if (mem->gmtfn25) return;
mem->gmtfn25=1;
  if ((10)==0) return; mem->var_float.R5_L_humidity=(float)(mem->var_Word.R5_L_humidity105)/((10)); 
 }
void fn28(void)
 {
 #ifdef PLC_SIM
 plcvar_t *mem = plcvar;
 #else
 plcvar_t *mem = &plcvar;
 #endif //PLC_SIM
 if (mem->gmtfn28) return;
mem->gmtfn28=1;
  if ((10)==0) return; mem->var_float.R6_humidity=(float)(mem->var_Word.R6_humidity6)/((10)); 
 }
void fn29(void)
 {
 #ifdef PLC_SIM
 plcvar_t *mem = plcvar;
 #else
 plcvar_t *mem = &plcvar;
 #endif //PLC_SIM
 if (mem->gmtfn29) return;
mem->gmtfn29=1;
  if ((10)==0) return; mem->var_float.R6_temp=(float)(mem->var_Word.R6_temp6)/((10)); 
 }
void fn30(void)
 {
 #ifdef PLC_SIM
 plcvar_t *mem = plcvar;
 #else
 plcvar_t *mem = &plcvar;
 #endif //PLC_SIM
 if (mem->gmtfn30) return;
mem->gmtfn30=1;
  if ((10)==0) return; mem->var_float.R6_L_humidity=(float)(mem->var_Word.R6_L_humidity106)/((10)); 
 }
void fn33(void)
 {
 #ifdef PLC_SIM
 plcvar_t *mem = plcvar;
 #else
 plcvar_t *mem = &plcvar;
 #endif //PLC_SIM
 if (mem->gmtfn33) return;
mem->gmtfn33=1;
  if ((10)==0) return; mem->var_float.R7_humidity=(float)(mem->var_Word.R7_humidity7)/((10)); 
 }
void fn34(void)
 {
 #ifdef PLC_SIM
 plcvar_t *mem = plcvar;
 #else
 plcvar_t *mem = &plcvar;
 #endif //PLC_SIM
 if (mem->gmtfn34) return;
mem->gmtfn34=1;
  if ((10)==0) return; mem->var_float.R7_temp=(float)(mem->var_Word.R7_temp7)/((10)); 
 }
void fn35(void)
 {
 #ifdef PLC_SIM
 plcvar_t *mem = plcvar;
 #else
 plcvar_t *mem = &plcvar;
 #endif //PLC_SIM
 if (mem->gmtfn35) return;
mem->gmtfn35=1;
  if ((10)==0) return; mem->var_float.R7_L_humidity=(float)(mem->var_Word.R7_L_humidity107)/((10)); 
 }
void fn38(void)
 {
 #ifdef PLC_SIM
 plcvar_t *mem = plcvar;
 #else
 plcvar_t *mem = &plcvar;
 #endif //PLC_SIM
 if (mem->gmtfn38) return;
mem->gmtfn38=1;
  if ((10)==0) return; mem->var_float.R8_humidity=(float)(mem->var_Word.R8_humidity8)/((10)); 
 }
void fn39(void)
 {
 #ifdef PLC_SIM
 plcvar_t *mem = plcvar;
 #else
 plcvar_t *mem = &plcvar;
 #endif //PLC_SIM
 if (mem->gmtfn39) return;
mem->gmtfn39=1;
  if ((10)==0) return; mem->var_float.R8_temp=(float)(mem->var_Word.R8_temp8)/((10)); 
 }
void fn40(void)
 {
 #ifdef PLC_SIM
 plcvar_t *mem = plcvar;
 #else
 plcvar_t *mem = &plcvar;
 #endif //PLC_SIM
 if (mem->gmtfn40) return;
mem->gmtfn40=1;
  if ((10)==0) return; mem->var_float.R8_L_humidity=(float)(mem->var_Word.R8_L_humidity108)/((10)); 
 }
void fn43(void)
 {
 #ifdef PLC_SIM
 plcvar_t *mem = plcvar;
 #else
 plcvar_t *mem = &plcvar;
 #endif //PLC_SIM
 if (mem->gmtfn43) return;
mem->gmtfn43=1;
  if ((10)==0) return; mem->var_float.R9_humidity=(float)(mem->var_Word.R9_humidity9)/((10)); 
 }
void fn44(void)
 {
 #ifdef PLC_SIM
 plcvar_t *mem = plcvar;
 #else
 plcvar_t *mem = &plcvar;
 #endif //PLC_SIM
 if (mem->gmtfn44) return;
mem->gmtfn44=1;
  if ((10)==0) return; mem->var_float.R9_temp=(float)(mem->var_Word.R9_temp9)/((10)); 
 }
void fn45(void)
 {
 #ifdef PLC_SIM
 plcvar_t *mem = plcvar;
 #else
 plcvar_t *mem = &plcvar;
 #endif //PLC_SIM
 if (mem->gmtfn45) return;
mem->gmtfn45=1;
  if ((10)==0) return; mem->var_float.R9_L_humidity=(float)(mem->var_Word.R9_L_humidity109)/((10)); 
 }
void fn48(void)
 {
 #ifdef PLC_SIM
 plcvar_t *mem = plcvar;
 #else
 plcvar_t *mem = &plcvar;
 #endif //PLC_SIM
 if (mem->gmtfn48) return;
mem->gmtfn48=1;
  if ((10)==0) return; mem->var_float.R10_humidity=(float)(mem->var_Word.R10_humidity10)/((10)); 
 }
void fn49(void)
 {
 #ifdef PLC_SIM
 plcvar_t *mem = plcvar;
 #else
 plcvar_t *mem = &plcvar;
 #endif //PLC_SIM
 if (mem->gmtfn49) return;
mem->gmtfn49=1;
  if ((10)==0) return; mem->var_float.R10_temp=(float)(mem->var_Word.R10_temp10)/((10)); 
 }
void fn50(void)
 {
 #ifdef PLC_SIM
 plcvar_t *mem = plcvar;
 #else
 plcvar_t *mem = &plcvar;
 #endif //PLC_SIM
 if (mem->gmtfn50) return;
mem->gmtfn50=1;
  if ((10)==0) return; mem->var_float.R10_L_humidity=(float)(mem->var_Word.R10_L_humidity110)/((10)); 
 }
void fn53(void)
 {
 #ifdef PLC_SIM
 plcvar_t *mem = plcvar;
 #else
 plcvar_t *mem = &plcvar;
 #endif //PLC_SIM
 if (mem->gmtfn53) return;
mem->gmtfn53=1;
  if ((10)==0) return; mem->var_float.R11_humidity=(float)(mem->var_Word.R11_humidity11)/((10)); 
 }
void fn54(void)
 {
 #ifdef PLC_SIM
 plcvar_t *mem = plcvar;
 #else
 plcvar_t *mem = &plcvar;
 #endif //PLC_SIM
 if (mem->gmtfn54) return;
mem->gmtfn54=1;
  if ((10)==0) return; mem->var_float.R11_temp=(float)(mem->var_Word.R11_temp11)/((10)); 
 }
void fn55(void)
 {
 #ifdef PLC_SIM
 plcvar_t *mem = plcvar;
 #else
 plcvar_t *mem = &plcvar;
 #endif //PLC_SIM
 if (mem->gmtfn55) return;
mem->gmtfn55=1;
  if ((10)==0) return; mem->var_float.R11_L_humidity=(float)(mem->var_Word.R11_L_humidity111)/((10)); 
 }
void fn58(void)
 {
 #ifdef PLC_SIM
 plcvar_t *mem = plcvar;
 #else
 plcvar_t *mem = &plcvar;
 #endif //PLC_SIM
 if (mem->gmtfn58) return;
mem->gmtfn58=1;
  if ((10)==0) return; mem->var_float.R12_humidity=(float)(mem->var_Word.R12_humidity12)/((10)); 
 }
void fn59(void)
 {
 #ifdef PLC_SIM
 plcvar_t *mem = plcvar;
 #else
 plcvar_t *mem = &plcvar;
 #endif //PLC_SIM
 if (mem->gmtfn59) return;
mem->gmtfn59=1;
  if ((10)==0) return; mem->var_float.R12_temp=(float)(mem->var_Word.R12_temp12)/((10)); 
 }
void fn60(void)
 {
 #ifdef PLC_SIM
 plcvar_t *mem = plcvar;
 #else
 plcvar_t *mem = &plcvar;
 #endif //PLC_SIM
 if (mem->gmtfn60) return;
mem->gmtfn60=1;
  if ((10)==0) return; mem->var_float.R12_L_humidity=(float)(mem->var_Word.R12_L_humidity112)/((10)); 
 }
void fn63(void)
 {
 #ifdef PLC_SIM
 plcvar_t *mem = plcvar;
 #else
 plcvar_t *mem = &plcvar;
 #endif //PLC_SIM
 if (mem->gmtfn63) return;
mem->gmtfn63=1;
  if ((10)==0) return; mem->var_float.R13_humidity=(float)(mem->var_Word.R13_humidity13)/((10)); 
 }
void fn64(void)
 {
 #ifdef PLC_SIM
 plcvar_t *mem = plcvar;
 #else
 plcvar_t *mem = &plcvar;
 #endif //PLC_SIM
 if (mem->gmtfn64) return;
mem->gmtfn64=1;
  if ((10)==0) return; mem->var_float.R13_temp=(float)(mem->var_Word.R13_temp13)/((10)); 
 }
void fn65(void)
 {
 #ifdef PLC_SIM
 plcvar_t *mem = plcvar;
 #else
 plcvar_t *mem = &plcvar;
 #endif //PLC_SIM
 if (mem->gmtfn65) return;
mem->gmtfn65=1;
  if ((10)==0) return; mem->var_float.R13_L_humidity=(float)(mem->var_Word.R13_L_humidity113)/((10)); 
 }
void fn68(void)
 {
 #ifdef PLC_SIM
 plcvar_t *mem = plcvar;
 #else
 plcvar_t *mem = &plcvar;
 #endif //PLC_SIM
 if (mem->gmtfn68) return;
mem->gmtfn68=1;
  if ((10)==0) return; mem->var_float.R14_humidity=(float)(mem->var_Word.R14_humidity14)/((10)); 
 }
void fn69(void)
 {
 #ifdef PLC_SIM
 plcvar_t *mem = plcvar;
 #else
 plcvar_t *mem = &plcvar;
 #endif //PLC_SIM
 if (mem->gmtfn69) return;
mem->gmtfn69=1;
  if ((10)==0) return; mem->var_float.R14_temp=(float)(mem->var_Word.R14_temp14)/((10)); 
 }
void fn70(void)
 {
 #ifdef PLC_SIM
 plcvar_t *mem = plcvar;
 #else
 plcvar_t *mem = &plcvar;
 #endif //PLC_SIM
 if (mem->gmtfn70) return;
mem->gmtfn70=1;
  if ((10)==0) return; mem->var_float.R14_L_humidity=(float)(mem->var_Word.R14_L_humidity114)/((10)); 
 }
void fn73(void)
 {
 #ifdef PLC_SIM
 plcvar_t *mem = plcvar;
 #else
 plcvar_t *mem = &plcvar;
 #endif //PLC_SIM
 if (mem->gmtfn73) return;
mem->gmtfn73=1;
  if ((10)==0) return; mem->var_float.R15_humidity=(float)(mem->var_Word.R15_humidity15)/((10)); 
 }
void fn74(void)
 {
 #ifdef PLC_SIM
 plcvar_t *mem = plcvar;
 #else
 plcvar_t *mem = &plcvar;
 #endif //PLC_SIM
 if (mem->gmtfn74) return;
mem->gmtfn74=1;
  if ((10)==0) return; mem->var_float.R15_temp=(float)(mem->var_Word.R15_temp15)/((10)); 
 }
void fn75(void)
 {
 #ifdef PLC_SIM
 plcvar_t *mem = plcvar;
 #else
 plcvar_t *mem = &plcvar;
 #endif //PLC_SIM
 if (mem->gmtfn75) return;
mem->gmtfn75=1;
  if ((10)==0) return; mem->var_float.R15_L_humidity=(float)(mem->var_Word.R15_L_humidity115)/((10)); 
 }
void fn78(void)
 {
 #ifdef PLC_SIM
 plcvar_t *mem = plcvar;
 #else
 plcvar_t *mem = &plcvar;
 #endif //PLC_SIM
 if (mem->gmtfn78) return;
mem->gmtfn78=1;
  if ((10)==0) return; mem->var_float.R16_humidity=(float)(mem->var_Word.R16_humidity16)/((10)); 
 }
void fn79(void)
 {
 #ifdef PLC_SIM
 plcvar_t *mem = plcvar;
 #else
 plcvar_t *mem = &plcvar;
 #endif //PLC_SIM
 if (mem->gmtfn79) return;
mem->gmtfn79=1;
  if ((10)==0) return; mem->var_float.R16_temp=(float)(mem->var_Word.R16_temp16)/((10)); 
 }
void fn80(void)
 {
 #ifdef PLC_SIM
 plcvar_t *mem = plcvar;
 #else
 plcvar_t *mem = &plcvar;
 #endif //PLC_SIM
 if (mem->gmtfn80) return;
mem->gmtfn80=1;
  if ((10)==0) return; mem->var_float.R16_L_humidity=(float)(mem->var_Word.R16_L_humidity116)/((10)); 
 }
void fn83(void)
 {
 #ifdef PLC_SIM
 plcvar_t *mem = plcvar;
 #else
 plcvar_t *mem = &plcvar;
 #endif //PLC_SIM
 if (mem->gmtfn83) return;
mem->gmtfn83=1;
  if ((10)==0) return; mem->var_float.R17_humidity=(float)(mem->var_Word.R17_humidity17)/((10)); 
 }
void fn84(void)
 {
 #ifdef PLC_SIM
 plcvar_t *mem = plcvar;
 #else
 plcvar_t *mem = &plcvar;
 #endif //PLC_SIM
 if (mem->gmtfn84) return;
mem->gmtfn84=1;
  if ((10)==0) return; mem->var_float.R17_temp=(float)(mem->var_Word.R17_temp17)/((10)); 
 }
void fn85(void)
 {
 #ifdef PLC_SIM
 plcvar_t *mem = plcvar;
 #else
 plcvar_t *mem = &plcvar;
 #endif //PLC_SIM
 if (mem->gmtfn85) return;
mem->gmtfn85=1;
  if ((10)==0) return; mem->var_float.R17_L_humidity=(float)(mem->var_Word.R17_L_humidity117)/((10)); 
 }
void fn88(void)
 {
 #ifdef PLC_SIM
 plcvar_t *mem = plcvar;
 #else
 plcvar_t *mem = &plcvar;
 #endif //PLC_SIM
 if (mem->gmtfn88) return;
mem->gmtfn88=1;
  if ((10)==0) return; mem->var_float.R18_humidity=(float)(mem->var_Word.R18_humidity18)/((10)); 
 }
void fn89(void)
 {
 #ifdef PLC_SIM
 plcvar_t *mem = plcvar;
 #else
 plcvar_t *mem = &plcvar;
 #endif //PLC_SIM
 if (mem->gmtfn89) return;
mem->gmtfn89=1;
  if ((10)==0) return; mem->var_float.R18_temp=(float)(mem->var_Word.R18_temp18)/((10)); 
 }
void fn90(void)
 {
 #ifdef PLC_SIM
 plcvar_t *mem = plcvar;
 #else
 plcvar_t *mem = &plcvar;
 #endif //PLC_SIM
 if (mem->gmtfn90) return;
mem->gmtfn90=1;
  if ((10)==0) return; mem->var_float.R18_L_humidity=(float)(mem->var_Word.R18_L_humidity118)/((10)); 
 }
void fn93(void)
 {
 #ifdef PLC_SIM
 plcvar_t *mem = plcvar;
 #else
 plcvar_t *mem = &plcvar;
 #endif //PLC_SIM
 if (mem->gmtfn93) return;
mem->gmtfn93=1;
  if ((10)==0) return; mem->var_float.R19_humidity=(float)(mem->var_Word.R19_humidity19)/((10)); 
 }
void fn94(void)
 {
 #ifdef PLC_SIM
 plcvar_t *mem = plcvar;
 #else
 plcvar_t *mem = &plcvar;
 #endif //PLC_SIM
 if (mem->gmtfn94) return;
mem->gmtfn94=1;
  if ((10)==0) return; mem->var_float.R19_temp=(float)(mem->var_Word.R19_temp19)/((10)); 
 }
void fn95(void)
 {
 #ifdef PLC_SIM
 plcvar_t *mem = plcvar;
 #else
 plcvar_t *mem = &plcvar;
 #endif //PLC_SIM
 if (mem->gmtfn95) return;
mem->gmtfn95=1;
  if ((10)==0) return; mem->var_float.R19_L_humidity=(float)(mem->var_Word.R19_L_humidity119)/((10)); 
 }
void fn98(void)
 {
 #ifdef PLC_SIM
 plcvar_t *mem = plcvar;
 #else
 plcvar_t *mem = &plcvar;
 #endif //PLC_SIM
 if (mem->gmtfn98) return;
mem->gmtfn98=1;
  if ((10)==0) return; mem->var_float.R20_humidity=(float)(mem->var_Word.R20_humidity20)/((10)); 
 }
void fn99(void)
 {
 #ifdef PLC_SIM
 plcvar_t *mem = plcvar;
 #else
 plcvar_t *mem = &plcvar;
 #endif //PLC_SIM
 if (mem->gmtfn99) return;
mem->gmtfn99=1;
  if ((10)==0) return; mem->var_float.R20_temp=(float)(mem->var_Word.R20_temp20)/((10)); 
 }
void fn100(void)
 {
 #ifdef PLC_SIM
 plcvar_t *mem = plcvar;
 #else
 plcvar_t *mem = &plcvar;
 #endif //PLC_SIM
 if (mem->gmtfn100) return;
mem->gmtfn100=1;
  if ((10)==0) return; mem->var_float.R20_L_humidity=(float)(mem->var_Word.R20_L_humidity120)/((10)); 
 }
void fn103(void)
 {
 #ifdef PLC_SIM
 plcvar_t *mem = plcvar;
 #else
 plcvar_t *mem = &plcvar;
 #endif //PLC_SIM
 if (mem->gmtfn103) return;
mem->gmtfn103=1;
  if ((10)==0) return; mem->var_float.R21_humidity=(float)(mem->var_Word.R21_humidity21)/((10)); 
 }
void fn104(void)
 {
 #ifdef PLC_SIM
 plcvar_t *mem = plcvar;
 #else
 plcvar_t *mem = &plcvar;
 #endif //PLC_SIM
 if (mem->gmtfn104) return;
mem->gmtfn104=1;
  if ((10)==0) return; mem->var_float.R21_temp=(float)(mem->var_Word.R21_temp21)/((10)); 
 }
void fn105(void)
 {
 #ifdef PLC_SIM
 plcvar_t *mem = plcvar;
 #else
 plcvar_t *mem = &plcvar;
 #endif //PLC_SIM
 if (mem->gmtfn105) return;
mem->gmtfn105=1;
  if ((10)==0) return; mem->var_float.R21_L_humidity=(float)(mem->var_Word.R21_L_humidity121)/((10)); 
 }
void fn108(void)
 {
 #ifdef PLC_SIM
 plcvar_t *mem = plcvar;
 #else
 plcvar_t *mem = &plcvar;
 #endif //PLC_SIM
 if (mem->gmtfn108) return;
mem->gmtfn108=1;
  if ((10)==0) return; mem->var_float.R22_humidity=(float)(mem->var_Word.R22_humidity22)/((10)); 
 }
void fn109(void)
 {
 #ifdef PLC_SIM
 plcvar_t *mem = plcvar;
 #else
 plcvar_t *mem = &plcvar;
 #endif //PLC_SIM
 if (mem->gmtfn109) return;
mem->gmtfn109=1;
  if ((10)==0) return; mem->var_float.R22_temp=(float)(mem->var_Word.R22_temp22)/((10)); 
 }
void fn110(void)
 {
 #ifdef PLC_SIM
 plcvar_t *mem = plcvar;
 #else
 plcvar_t *mem = &plcvar;
 #endif //PLC_SIM
 if (mem->gmtfn110) return;
mem->gmtfn110=1;
  if ((10)==0) return; mem->var_float.R22_L_humidity=(float)(mem->var_Word.R22_L_humidity122)/((10)); 
 }
void fn113(void)
 {
 #ifdef PLC_SIM
 plcvar_t *mem = plcvar;
 #else
 plcvar_t *mem = &plcvar;
 #endif //PLC_SIM
 if (mem->gmtfn113) return;
mem->gmtfn113=1;
  if ((10)==0) return; mem->var_float.R23_humidity=(float)(mem->var_Word.R23_humidity23)/((10)); 
 }
void fn114(void)
 {
 #ifdef PLC_SIM
 plcvar_t *mem = plcvar;
 #else
 plcvar_t *mem = &plcvar;
 #endif //PLC_SIM
 if (mem->gmtfn114) return;
mem->gmtfn114=1;
  if ((10)==0) return; mem->var_float.R23_temp=(float)(mem->var_Word.R23_temp23)/((10)); 
 }
void fn115(void)
 {
 #ifdef PLC_SIM
 plcvar_t *mem = plcvar;
 #else
 plcvar_t *mem = &plcvar;
 #endif //PLC_SIM
 if (mem->gmtfn115) return;
mem->gmtfn115=1;
  if ((10)==0) return; mem->var_float.R23_L_humidity=(float)(mem->var_Word.R23_L_humidity123)/((10)); 
 }
void fn118(void)
 {
 #ifdef PLC_SIM
 plcvar_t *mem = plcvar;
 #else
 plcvar_t *mem = &plcvar;
 #endif //PLC_SIM
 if (mem->gmtfn118) return;
mem->gmtfn118=1;
  if ((10)==0) return; mem->var_float.R24_humidity=(float)(mem->var_Word.R24_humidity24)/((10)); 
 }
void fn119(void)
 {
 #ifdef PLC_SIM
 plcvar_t *mem = plcvar;
 #else
 plcvar_t *mem = &plcvar;
 #endif //PLC_SIM
 if (mem->gmtfn119) return;
mem->gmtfn119=1;
  if ((10)==0) return; mem->var_float.R24_temp=(float)(mem->var_Word.R24_temp24)/((10)); 
 }
void fn120(void)
 {
 #ifdef PLC_SIM
 plcvar_t *mem = plcvar;
 #else
 plcvar_t *mem = &plcvar;
 #endif //PLC_SIM
 if (mem->gmtfn120) return;
mem->gmtfn120=1;
  if ((10)==0) return; mem->var_float.R24_L_humidity=(float)(mem->var_Word.R24_L_humidity124)/((10)); 
 }
void fn123(void)
 {
 #ifdef PLC_SIM
 plcvar_t *mem = plcvar;
 #else
 plcvar_t *mem = &plcvar;
 #endif //PLC_SIM
 if (mem->gmtfn123) return;
mem->gmtfn123=1;
 mem->var_Word.ortlama_1_9=mem->var_float.R1_humidity+mem->var_float.R9_humidity; 
 }
void fn124(void)
 {
 #ifdef PLC_SIM
 plcvar_t *mem = plcvar;
 #else
 plcvar_t *mem = &plcvar;
 #endif //PLC_SIM
 if (mem->gmtfn124) return;
mem->gmtfn124=1;
 mem->var_Word.ortlama_1_9_17=mem->var_Word.ortlama_1_9+mem->var_float.R17_humidity; 
 }
void fn125(void)
 {
 #ifdef PLC_SIM
 plcvar_t *mem = plcvar;
 #else
 plcvar_t *mem = &plcvar;
 #endif //PLC_SIM
 if (mem->gmtfn125) return;
mem->gmtfn125=1;
  if ((3)==0) return; mem->var_Word.son_ortlama_1_9_17=(float)(mem->var_Word.ortlama_1_9_17)/((3)); 
 }
void fn132(void)
 {
 #ifdef PLC_SIM
 plcvar_t *mem = plcvar;
 #else
 plcvar_t *mem = &plcvar;
 #endif //PLC_SIM
 if (mem->gmtfn132) return;
mem->gmtfn132=1;
 mem->var_Word.ortlama_2_10=mem->var_float.R2_humidity+mem->var_float.R10_humidity; 
 }
void fn133(void)
 {
 #ifdef PLC_SIM
 plcvar_t *mem = plcvar;
 #else
 plcvar_t *mem = &plcvar;
 #endif //PLC_SIM
 if (mem->gmtfn133) return;
mem->gmtfn133=1;
 mem->var_Word.ortlama_2_10_18=mem->var_Word.ortlama_2_10+mem->var_float.R18_humidity; 
 }
void fn134(void)
 {
 #ifdef PLC_SIM
 plcvar_t *mem = plcvar;
 #else
 plcvar_t *mem = &plcvar;
 #endif //PLC_SIM
 if (mem->gmtfn134) return;
mem->gmtfn134=1;
  if ((3)==0) return; mem->var_Word.son_ortlama_2_10_18=(float)(mem->var_Word.ortlama_2_10_18)/((3)); 
 }
void fn141(void)
 {
 #ifdef PLC_SIM
 plcvar_t *mem = plcvar;
 #else
 plcvar_t *mem = &plcvar;
 #endif //PLC_SIM
 if (mem->gmtfn141) return;
mem->gmtfn141=1;
 mem->var_Word.ortlama_3_11=mem->var_float.R3_humidity+mem->var_float.R11_humidity; 
 }
void fn142(void)
 {
 #ifdef PLC_SIM
 plcvar_t *mem = plcvar;
 #else
 plcvar_t *mem = &plcvar;
 #endif //PLC_SIM
 if (mem->gmtfn142) return;
mem->gmtfn142=1;
 mem->var_Word.ortlama_3_11_19=mem->var_Word.ortlama_3_11+mem->var_float.R19_humidity; 
 }
void fn143(void)
 {
 #ifdef PLC_SIM
 plcvar_t *mem = plcvar;
 #else
 plcvar_t *mem = &plcvar;
 #endif //PLC_SIM
 if (mem->gmtfn143) return;
mem->gmtfn143=1;
  if ((3)==0) return; mem->var_Word.son_ortlama_3_11_19=(float)(mem->var_Word.ortlama_3_11_19)/((3)); 
 }
void fn150(void)
 {
 #ifdef PLC_SIM
 plcvar_t *mem = plcvar;
 #else
 plcvar_t *mem = &plcvar;
 #endif //PLC_SIM
 if (mem->gmtfn150) return;
mem->gmtfn150=1;
 mem->var_Word.ortlama_4_12=mem->var_float.R4_humidity+mem->var_float.R12_humidity; 
 }
void fn151(void)
 {
 #ifdef PLC_SIM
 plcvar_t *mem = plcvar;
 #else
 plcvar_t *mem = &plcvar;
 #endif //PLC_SIM
 if (mem->gmtfn151) return;
mem->gmtfn151=1;
 mem->var_Word.ortlama_4_12_20=mem->var_Word.ortlama_4_12+mem->var_float.R20_humidity; 
 }
void fn152(void)
 {
 #ifdef PLC_SIM
 plcvar_t *mem = plcvar;
 #else
 plcvar_t *mem = &plcvar;
 #endif //PLC_SIM
 if (mem->gmtfn152) return;
mem->gmtfn152=1;
  if ((3)==0) return; mem->var_Word.son_ortlama_4_12_20=(float)(mem->var_Word.ortlama_4_12_20)/((3)); 
 }
void fn159(void)
 {
 #ifdef PLC_SIM
 plcvar_t *mem = plcvar;
 #else
 plcvar_t *mem = &plcvar;
 #endif //PLC_SIM
 if (mem->gmtfn159) return;
mem->gmtfn159=1;
 mem->var_Word.ortlama_5_13=mem->var_float.R5_humidity+mem->var_float.R13_humidity; 
 }
void fn160(void)
 {
 #ifdef PLC_SIM
 plcvar_t *mem = plcvar;
 #else
 plcvar_t *mem = &plcvar;
 #endif //PLC_SIM
 if (mem->gmtfn160) return;
mem->gmtfn160=1;
 mem->var_Word.ortlama_5_13_21=mem->var_Word.ortlama_5_13+mem->var_float.R21_humidity; 
 }
void fn161(void)
 {
 #ifdef PLC_SIM
 plcvar_t *mem = plcvar;
 #else
 plcvar_t *mem = &plcvar;
 #endif //PLC_SIM
 if (mem->gmtfn161) return;
mem->gmtfn161=1;
  if ((3)==0) return; mem->var_Word.son_ortlama_5_13_21=(float)(mem->var_Word.ortlama_5_13_21)/((3)); 
 }
void fn168(void)
 {
 #ifdef PLC_SIM
 plcvar_t *mem = plcvar;
 #else
 plcvar_t *mem = &plcvar;
 #endif //PLC_SIM
 if (mem->gmtfn168) return;
mem->gmtfn168=1;
 mem->var_Word.ortlama_6_14=mem->var_float.R6_humidity+mem->var_float.R14_humidity; 
 }
void fn169(void)
 {
 #ifdef PLC_SIM
 plcvar_t *mem = plcvar;
 #else
 plcvar_t *mem = &plcvar;
 #endif //PLC_SIM
 if (mem->gmtfn169) return;
mem->gmtfn169=1;
 mem->var_Word.ortlama_6_14_22=mem->var_Word.ortlama_6_14+mem->var_float.R22_humidity; 
 }
void fn170(void)
 {
 #ifdef PLC_SIM
 plcvar_t *mem = plcvar;
 #else
 plcvar_t *mem = &plcvar;
 #endif //PLC_SIM
 if (mem->gmtfn170) return;
mem->gmtfn170=1;
  if ((3)==0) return; mem->var_Word.son_ortlama_6_14_22=(float)(mem->var_Word.ortlama_6_14_22)/((3)); 
 }
void fn177(void)
 {
 #ifdef PLC_SIM
 plcvar_t *mem = plcvar;
 #else
 plcvar_t *mem = &plcvar;
 #endif //PLC_SIM
 if (mem->gmtfn177) return;
mem->gmtfn177=1;
 mem->var_Word.ortlama_7_15=mem->var_float.R7_humidity+mem->var_float.R15_humidity; 
 }
void fn178(void)
 {
 #ifdef PLC_SIM
 plcvar_t *mem = plcvar;
 #else
 plcvar_t *mem = &plcvar;
 #endif //PLC_SIM
 if (mem->gmtfn178) return;
mem->gmtfn178=1;
 mem->var_Word.ortlama_7_15_23=mem->var_Word.ortlama_7_15+mem->var_float.R23_humidity; 
 }
void fn179(void)
 {
 #ifdef PLC_SIM
 plcvar_t *mem = plcvar;
 #else
 plcvar_t *mem = &plcvar;
 #endif //PLC_SIM
 if (mem->gmtfn179) return;
mem->gmtfn179=1;
  if ((3)==0) return; mem->var_Word.son_ortlama_7_15_23=(float)(mem->var_Word.ortlama_7_15_23)/((3)); 
 }
void fn186(void)
 {
 #ifdef PLC_SIM
 plcvar_t *mem = plcvar;
 #else
 plcvar_t *mem = &plcvar;
 #endif //PLC_SIM
 if (mem->gmtfn186) return;
mem->gmtfn186=1;
 mem->var_Word.ortlama_8_16=mem->var_float.R8_humidity+mem->var_float.R16_humidity; 
 }
void fn187(void)
 {
 #ifdef PLC_SIM
 plcvar_t *mem = plcvar;
 #else
 plcvar_t *mem = &plcvar;
 #endif //PLC_SIM
 if (mem->gmtfn187) return;
mem->gmtfn187=1;
 mem->var_Word.ortlama_8_16_24=mem->var_Word.ortlama_8_16+mem->var_float.R24_humidity; 
 }
void fn188(void)
 {
 #ifdef PLC_SIM
 plcvar_t *mem = plcvar;
 #else
 plcvar_t *mem = &plcvar;
 #endif //PLC_SIM
 if (mem->gmtfn188) return;
mem->gmtfn188=1;
  if ((3)==0) return; mem->var_Word.son_ortlama_8_16_24=(float)(mem->var_Word.ortlama_8_16_24)/((3)); 
 }
 
int app_proc(void)
{

#ifdef PLC_SIM
plcvar_t *mem = plcvar;
#else
plcvar_t *mem = &plcvar;
#endif //PLC_SIM
flash_dummy_degisken=0;
for (int i=0; i<280; i++)
#ifdef PLC_SIM
    mem->IP[i] = mem->IP_Force1[i];
#else
    mem->IP[i] = (mem->IP[i] & mem->IP_Force0[i]) || (mem->IP_Force1[i]);
#endif
if (cl_vrunonce){
  cl_FPowerOnFunction();
  I32 params[3];
  params[0] = (0 );
  params[1] = 1500;
  DRV_IOCTL(hso, IOCTL_HSO_SETVALUE, params);
  cl_vrunonce=0;}
 mem->var_Int.CPU_WMIStatus =SB[15];if ( (SB[80]) && (!mem->SB80Esk)){
mem->SB80Esk=1;
mem->var_Int.CPU_COM1_Status=SI[86];
mem->var_Int.CPU_COM1_ErrVal=SI[87];
}
if(SB[80] && (mem->var_Int.CPU_COM1_Status==0)){
mem->var_Int.CPU_COM1_ErrVal=0;
SB[80]=0;
mem->SB80Esk=0;
}
mem->var_bit.CPU_Osc_1ms = (SB[5]&1);mem->var_bit.CPU_Osc_10ms = (SB[6]&1);mem->var_bit.CPU_Osc_100ms = (SB[2]&1);mem->var_bit.CPU_Osc_500ms = (SB[3]&1);mem->var_bit.CPU_Osc_1000ms = (SB[4]&1);
#ifdef PLC_SIM
#else
if (mem->plc_lad_delay_sayac < 4){ if ( (mem->var_bit.CPU_Osc_1000ms &!(mem->SB1SnEsk)) || (!mem->var_bit.CPU_Osc_1000ms && (mem->SB1SnEsk)) ){  mem->plc_lad_delay_sayac++;} mem->SB1SnEsk=mem->var_bit.CPU_Osc_1000ms; return 1;}
#endif 
mem->var_Int.CPU_LadderFreq = SI[30];mem->var_Word.CPU_InpWord = cl_fGetWord( mem->IP[0],  mem->IP[1],  mem->IP[2],  mem->IP[3],  mem->IP[4],  mem->IP[5],  mem->IP[6],  mem->IP[7],  mem->IP[8], 0,0,0,0,0,0,0);cl_fSetWord( &mem->var_Word.CPU_OutWord, &mem->var_Word.CPU_OutWordHlp, &mem->QP[0], &mem->QP[1], &mem->QP[2], &mem->QP[3], &mem->QP[4], &mem->QP[5],NULL , NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);

mem->var_Word.Exp01_InpWord_01 = cl_fGetWord( mem->IP[16],  mem->IP[17],  mem->IP[18],  mem->IP[19],  mem->IP[20],  mem->IP[21],  mem->IP[22],  mem->IP[23], 0,0,0,0,0,0,0,0);

cl_fSetWord( &mem->var_Word.Exp01_OutWord_01, &mem->var_Word.Exp01_OutWordHlp_01, &mem->QP[16], &mem->QP[17], &mem->QP[18], &mem->QP[19], &mem->QP[20], &mem->QP[21], &mem->QP[22], &mem->QP[23],NULL , NULL, NULL, NULL, NULL, NULL, NULL, NULL);

if (cl_vrunonce2){
cl_vrunonce2=0;}
if (  (mem->var_bit.CPU_Osc_1ms &!(mem->SB5Esk)) || (!mem->var_bit.CPU_Osc_1ms && (mem->SB5Esk))  )
 cl_f1ms();
 mem->SB5Esk=mem->var_bit.CPU_Osc_1ms;

mem->gmtfn1=0;
mem->gmtfn2=0;
mem->gmtfn3=0;
mem->gmtfn4=0;
mem->gmtfn5=0;
mem->gmtfn7=0;
mem->gmtfn8=0;
mem->gmtfn9=0;
mem->gmtfn10=0;
mem->gmtfn13=0;
mem->gmtfn14=0;
mem->gmtfn15=0;
mem->gmtfn18=0;
mem->gmtfn19=0;
mem->gmtfn20=0;
mem->gmtfn23=0;
mem->gmtfn24=0;
mem->gmtfn25=0;
mem->gmtfn28=0;
mem->gmtfn29=0;
mem->gmtfn30=0;
mem->gmtfn33=0;
mem->gmtfn34=0;
mem->gmtfn35=0;
mem->gmtfn38=0;
mem->gmtfn39=0;
mem->gmtfn40=0;
mem->gmtfn43=0;
mem->gmtfn44=0;
mem->gmtfn45=0;
mem->gmtfn48=0;
mem->gmtfn49=0;
mem->gmtfn50=0;
mem->gmtfn53=0;
mem->gmtfn54=0;
mem->gmtfn55=0;
mem->gmtfn58=0;
mem->gmtfn59=0;
mem->gmtfn60=0;
mem->gmtfn63=0;
mem->gmtfn64=0;
mem->gmtfn65=0;
mem->gmtfn68=0;
mem->gmtfn69=0;
mem->gmtfn70=0;
mem->gmtfn73=0;
mem->gmtfn74=0;
mem->gmtfn75=0;
mem->gmtfn78=0;
mem->gmtfn79=0;
mem->gmtfn80=0;
mem->gmtfn83=0;
mem->gmtfn84=0;
mem->gmtfn85=0;
mem->gmtfn88=0;
mem->gmtfn89=0;
mem->gmtfn90=0;
mem->gmtfn93=0;
mem->gmtfn94=0;
mem->gmtfn95=0;
mem->gmtfn98=0;
mem->gmtfn99=0;
mem->gmtfn100=0;
mem->gmtfn103=0;
mem->gmtfn104=0;
mem->gmtfn105=0;
mem->gmtfn108=0;
mem->gmtfn109=0;
mem->gmtfn110=0;
mem->gmtfn113=0;
mem->gmtfn114=0;
mem->gmtfn115=0;
mem->gmtfn118=0;
mem->gmtfn119=0;
mem->gmtfn120=0;
mem->gmtfn123=0;
mem->gmtfn124=0;
mem->gmtfn125=0;
mem->gmtfn132=0;
mem->gmtfn133=0;
mem->gmtfn134=0;
mem->gmtfn141=0;
mem->gmtfn142=0;
mem->gmtfn143=0;
mem->gmtfn150=0;
mem->gmtfn151=0;
mem->gmtfn152=0;
mem->gmtfn159=0;
mem->gmtfn160=0;
mem->gmtfn161=0;
mem->gmtfn168=0;
mem->gmtfn169=0;
mem->gmtfn170=0;
mem->gmtfn177=0;
mem->gmtfn178=0;
mem->gmtfn179=0;
mem->gmtfn186=0;
mem->gmtfn187=0;
mem->gmtfn188=0;

fn1();

fn2();

fn3();

fn4();

fn5();
 mem->var_Word.R1_salt_co=mem->var_Word.R1_salt_co; 

fn7();

fn8();

fn9();

fn10();
 mem->var_Word.R2_ec=mem->var_Word.R2_ec; 
 mem->var_Word.R2_salt=mem->var_Word.R2_salt; 

fn13();

fn14();

fn15();
 mem->var_Word.R3_ec=mem->var_Word.R3_ec; 
 mem->var_Word.R3_salt=mem->var_Word.R3_salt; 

fn18();

fn19();

fn20();
 mem->var_Word.R4_ec=mem->var_Word.R4_ec; 
 mem->var_Word.R4_salt=mem->var_Word.R4_salt; 

fn23();

fn24();

fn25();
 mem->var_Word.R5_ec=mem->var_Word.R5_ec; 
 mem->var_Word.R5_salt=mem->var_Word.R5_salt; 

fn28();

fn29();

fn30();
 mem->var_Word.R6_ec=mem->var_Word.R6_ec; 
 mem->var_Word.R6_salt=mem->var_Word.R6_salt; 

fn33();

fn34();

fn35();
 mem->var_Word.R7_ec=mem->var_Word.R7_ec; 
 mem->var_Word.R7_salt=mem->var_Word.R7_salt; 

fn38();

fn39();

fn40();
 mem->var_Word.R8_ec=mem->var_Word.R8_ec; 
 mem->var_Word.R8_salt=mem->var_Word.R8_salt; 

fn43();

fn44();

fn45();
 mem->var_Word.R9_ec=mem->var_Word.R9_ec; 
 mem->var_Word.R9_salt=mem->var_Word.R9_salt; 

fn48();

fn49();

fn50();
 mem->var_Word.R10_ec=mem->var_Word.R10_ec; 
 mem->var_Word.R10_salt=mem->var_Word.R10_salt; 

fn53();

fn54();

fn55();
 mem->var_Word.R11_ec=mem->var_Word.R11_ec; 
 mem->var_Word.R11_salt=mem->var_Word.R11_salt; 

fn58();

fn59();

fn60();
 mem->var_Word.R12_ec=mem->var_Word.R12_ec; 
 mem->var_Word.R12_salt=mem->var_Word.R12_salt; 

fn63();

fn64();

fn65();
 mem->var_Word.R13_ec=mem->var_Word.R13_ec; 
 mem->var_Word.R13_salt=mem->var_Word.R13_salt; 

fn68();

fn69();

fn70();
 mem->var_Word.R14_ec=mem->var_Word.R14_ec; 
 mem->var_Word.R14_salt=mem->var_Word.R14_salt; 

fn73();

fn74();

fn75();
 mem->var_Word.R15_ec=mem->var_Word.R15_ec; 
 mem->var_Word.R15_salt=mem->var_Word.R15_salt; 

fn78();

fn79();

fn80();
 mem->var_Word.R16_ec=mem->var_Word.R16_ec; 
 mem->var_Word.R16_salt=mem->var_Word.R16_salt; 

fn83();

fn84();

fn85();
 mem->var_Word.R17_ec=mem->var_Word.R17_ec; 
 mem->var_Word.R17_salt=mem->var_Word.R17_salt; 

fn88();

fn89();

fn90();
 mem->var_Word.R18_ec=mem->var_Word.R18_ec; 
 mem->var_Word.R18_salt=mem->var_Word.R18_salt; 

fn93();

fn94();

fn95();
 mem->var_Word.R19_ec=mem->var_Word.R19_ec; 
 mem->var_Word.R19_salt=mem->var_Word.R19_salt; 

fn98();

fn99();

fn100();
 mem->var_Word.R20_ec=mem->var_Word.R20_ec; 
 mem->var_Word.R20_salt=mem->var_Word.R20_salt; 

fn103();

fn104();

fn105();
 mem->var_Word.R21_ec=mem->var_Word.R21_ec; 
 mem->var_Word.R21_salt=mem->var_Word.R21_salt; 

fn108();

fn109();

fn110();
 mem->var_Word.R22_ec=mem->var_Word.R22_ec; 
 mem->var_Word.R22_salt=mem->var_Word.R22_salt; 

fn113();

fn114();

fn115();
 mem->var_Word.R23_ec=mem->var_Word.R23_ec; 
 mem->var_Word.R23_salt=mem->var_Word.R23_salt; 

fn118();

fn119();

fn120();
 mem->var_Word.R24_ec=mem->var_Word.R24_ec; 
 mem->var_Word.R24_salt=mem->var_Word.R24_salt; 

fn123();

fn124();

fn125();

fn132();
fn133();
fn134();
fn141();
fn142();
fn143();
fn150();
fn151();
fn152();
fn159();
fn160();
fn161();
fn168();
fn169();
fn170();
fn177();
fn178();
fn179();
fn186();
fn187();
fn188();

// --- UNIFIED AUTO (3-PLOT AVG) & MANUAL (HMI TOUCH VALVE) CONTROL FOR ZONES 1..8 ---
{
    U8 vana_arr[8] = {
        mem->var_bit.vana1, mem->var_bit.vana2, mem->var_bit.vana3, mem->var_bit.vana4,
        mem->var_bit.vana5, mem->var_bit.vana6, mem->var_bit.vana7, mem->var_bit.vana8
    };
    U16 avg_arr[8] = {
        mem->var_Word.son_ortlama_1_9_17, mem->var_Word.son_ortlama_2_10_18,
        mem->var_Word.son_ortlama_3_11_19, mem->var_Word.son_ortlama_4_12_20,
        mem->var_Word.son_ortlama_5_13_21, mem->var_Word.son_ortlama_6_14_22,
        mem->var_Word.son_ortlama_7_15_23, mem->var_Word.son_ortlama_8_16_24
    };
    U8 qp_idx[8] = { 0, 1, 23, 22, 2, 3, 4, 5 };
    if (mem->var_bit.dummydeg_gmt_1 != 0xA5) {
        U8 init_prev = 0;
        U8 init_auto = 0;
        int z;
        for (z = 0; z < 8; z++) {
            if (vana_arr[z]) {
                init_prev |= (1 << z);
                if (mem->QP[qp_idx[z]] || avg_arr[z] <= 45) {
                    init_auto |= (1 << z);
                }
            }
        }
        mem->var_bit.dummydeg_gmt_0 = init_prev;
        mem->var_bit.dummydeg_gmt_2 = init_auto;
        mem->var_bit.dummydeg_gmt_1 = 0xA5;
    }
    U8 prev_mask = mem->var_bit.dummydeg_gmt_0;
    U8 auto_mask = mem->var_bit.dummydeg_gmt_2;
    int z;
    for (z = 0; z < 8; z++) {
        U8 bit = (1 << z);
        U8 cur_v = vana_arr[z] ? 1 : 0;
        U8 prv_v = (prev_mask & bit) ? 1 : 0;
        if (cur_v) {
            if (!prv_v) {
                if (avg_arr[z] <= 45) auto_mask |= bit;
                else auto_mask &= ~bit;
            }
            if (avg_arr[z] <= 45) {
                auto_mask |= bit;
            } else if (avg_arr[z] >= 80) {
                auto_mask &= ~bit;
            }
            mem->QP[qp_idx[z]] = (auto_mask & bit) ? 1 : 0;
            prev_mask |= bit;
        } else {
            if (prv_v) {
                mem->QP[qp_idx[z]] = 0;
                auto_mask &= ~bit;
            }
            // While in Manual Mode (cur_v == 0 && prv_v == 0), do NOT overwrite mem->QP[qp_idx[z]]!
            prev_mask &= ~bit;
        }
    }
    mem->var_bit.dummydeg_gmt_0 = prev_mask;
    mem->var_bit.dummydeg_gmt_2 = auto_mask;
}


return 1;
}

#if IMG_REVISION >= 527

int getusTick(int timold) {
U16 tim7_old_val=timold;
U16  tim7_val=0,dbg_tim7_diff=0;
tim7_val = SI[114];
if(tim7_old_val <= tim7_val) {
 dbg_tim7_diff = tim7_val - tim7_old_val;
}
else {
 dbg_tim7_diff = tim7_val + (65535 - tim7_old_val);
}
tim7_old_val = tim7_val;

return dbg_tim7_diff;
}
#endif	


/*******************************************************************************
* Function Name  : event_hso_onfinished
* Description    : High speed outputs OnFinished event.
* Input          : None
* Output         : None
* Return         : None
*******************************************************************************/
void event_hso_onfinished(U32 chan, U32 count)
{
 #ifdef PLC_SIM
 plcvar_t *mem = plcvar;
 #else
 plcvar_t *mem = &plcvar;
 #endif //PLC_SIM
 
   int params[2];
   
    SI[80+chan] = count;
    if (chan==0)
		gmt_HSO0anlik = count;
    if (chan==1)
		gmt_HSO1anlik = count;
    if (chan==2)
		gmt_HSO2anlik = count;	

	#if IMG_REVISION <= 521
       SB[53+chan] = 0;	
	#endif	
	

/*
  
 #ifdef def_gmt_HSO0busy
 if (chan==0)
   def_gmt_HSO0busy=0;
 #endif 

 #ifdef def_gmt_HSO1busy
 if (chan==1)
   def_gmt_HSO1busy=0;
 #endif 

 #ifdef def_gmt_HSO2busy
 if (chan==2)
   def_gmt_HSO2busy=0;
 #endif 
   */
   
    params[0] = chan;
    params[1] = count;
    DRV_IOCTL(hso, IOCTL_HSO_SETVALUE, params);	
}//event_hso_onfinished


/*
*********************************************************************************************************
*                                            SIMULATION SECTION
*********************************************************************************************************
*/

#ifdef PLC_SIM

/*
*********************************************************************************************************
*                                             INCLUDE FILES
*********************************************************************************************************
*/


/*
*********************************************************************************************************
*                                           LOCAL DEFINITIONS
*********************************************************************************************************
*/

#define PROCESS_TERMINATEgmt	2000
#define LOAD_TICK_SECOND	1000
#define LOAD_TICK_500MS		500
#define LOAD_TICK_100MS		100
#define LOAD_TICK_50MS		50
#define LOAD_TICK_10MS		10

#define BUF_SIZE 			(32*1024)

const TCHAR szName[] = TEXT("Local\\GMT_SIM_SHMEM");

/*
*********************************************************************************************************
*                                            LOCAL MACROS
*********************************************************************************************************
*/

#define PLC_TGL_1ms()		(SB[5]^=1)
#define PLC_TGL_10ms()		(SB[6]^=1)
#define PLC_TGL_100ms()		(SB[2]^=1)
#define PLC_TGL_500ms()		(SB[3]^=1)
#define PLC_TGL_1000ms()	(SB[4]^=1)

/*
*********************************************************************************************************
*                                           LOCAL VARIABLES
*********************************************************************************************************
*/

static BOOL app_is_running;
static LARGE_INTEGER t1, t2;
static LARGE_INTEGER freq;
static double elapsedTime;
static MMRESULT plcTimer;

struct
{
	U32 tick_ms;
	U32 tick_sec;
	U32 load_10ms;
	U32 load_50ms;
	U32 load_100ms;
	U32 load_500ms;
	U32 load_1000ms;
} sys_tick;


/*******************************************************************************
* Function Name  : clock_init
* Description    : None
* Input          : None
* Output         : None
* Return         : None
*******************************************************************************/
static void clock_init(void)
{
    // Clear tick value
	memset((void*)&sys_tick, 0, sizeof(sys_tick));

    // Load tick value
	sys_tick.load_1000ms = LOAD_TICK_SECOND;
	sys_tick.load_500ms  = LOAD_TICK_500MS;
	sys_tick.load_100ms  = LOAD_TICK_100MS;
	sys_tick.load_50ms   = LOAD_TICK_50MS;
	sys_tick.load_10ms   = LOAD_TICK_10MS;
}//clock_init


/*******************************************************************************
* Function Name  : PLC_TickProc
* Description    : Must be called every 1ms.
* Input          : None
* Output         : None
* Return         : None
*******************************************************************************/
static void PLC_TickProc(U32 tick)
{
	//
	// Toggle PLC 1ms timer flag.
	//
	PLC_TGL_1ms();

    //
    // 1000ms time tick.
    //
	if (!--sys_tick.load_1000ms)
	{
		// reload the value
		sys_tick.load_1000ms = LOAD_TICK_SECOND;

		// increment the system time
		sys_tick.tick_sec++;

    	// Toggle PLC 1000ms timer flag.
		PLC_TGL_1000ms();
	}//if

    //
    // 500ms time tick.
    //
	if (!--sys_tick.load_500ms)
	{
		// reload the value
		sys_tick.load_500ms = LOAD_TICK_500MS;

    	// Toggle PLC 500ms timer flag.
		PLC_TGL_500ms();
	}//if

    //
    // 100ms time tick.
    //
	if (!--sys_tick.load_100ms)
	{
		// reload the value
		sys_tick.load_100ms = LOAD_TICK_100MS;

    	// Toggle PLC 100ms timer flag.
		PLC_TGL_100ms();
	}//if

    //
    // 10ms time tick.
    //
	if (!--sys_tick.load_10ms)
	{
		// reload the value
		sys_tick.load_10ms = LOAD_TICK_10MS;

    	// Toggle PLC 10ms timer flag.
		PLC_TGL_10ms();
	}//if

    //
	// Check for process termination time
    //
	//if (plcvar->ref_degisken)
	{
		if (++plcvar->ref_degisken >= PROCESS_TERMINATEgmt)
		{
			// clear the run flag
			app_is_running = FALSE;
		}//if
	}//if
}//PLC_TickProc


/*******************************************************************************
* Function Name  : PLC_AppProc
* Description    : None
* Input          : None
* Output         : None
* Return         : None
*******************************************************************************/
void WINAPI PLC_AppProc(U32 uTimerID, U32 uMsg, DWORD dwUser, DWORD dw1, DWORD dw2)
{
	//---------------------------------------------------------------
	// measure the calling period as microsecond
	//---------------------------------------------------------------

    // get ticks per second
    QueryPerformanceFrequency(&freq);

    // get the stop count value
	QueryPerformanceCounter(&t2);

	// compute the elapsed time in microsecond
	elapsedTime = (t2.QuadPart - t1.QuadPart) * 1000000.0 / freq.QuadPart;

    // get the start count value
    QueryPerformanceCounter(&t1);
	//---------------------------------------------------------------

	// call the PLC application loop
	if (app_proc())
	{
		// call the library update functions
		lib_math_update(0, 0);
		lib_mem_update(0, 0);

		// call the driver update functions
		drv_din_update(0, 0);
		drv_dout_update(0, 0);
		drv_ain_update(0, 0);
		drv_aout_update(0, 0);
		drv_sen_update(0, 0);
		drv_ldc_update(0, 0);
		drv_enc_update(0, 0);
		drv_hso_update(0, 0);
		drv_exp_update(0, 0);
		drv_rtc_update(0, 0);
		drv_com_update(0, 0);
		drv_wmi_update(0, 0);

		// call the tick process
		PLC_TickProc(elapsedTime);

		// is the application running ?
		if (app_is_running)
		{
			// restart the timer
			if ((plcTimer = timeSetEvent(1, 0, PLC_AppProc, 0, TIME_ONESHOT)) == 0)
			{
				// there is an error !!!
				// so exit from PLC loop
				app_is_running = FALSE;
			}//if
		}//if
	}//if
	// there is exit request from the PLC application
	else
	{
    	// so exit from PLC loop
    	app_is_running = FALSE;
	}//else
}//PLC_TimerProc


/*******************************************************************************
* Function Name  : main
* Description    : None
* Input          : None
* Output         : None
* Return         : None
*******************************************************************************/
int main(void)
{
	// create the memory mapped file
	HANDLE hMapFile = CreateFileMapping(INVALID_HANDLE_VALUE,  	// use paging file
										NULL,                 	// default security
										PAGE_READWRITE,       	// read/write access
										0,                     	// maximum object size (high-order DWORD)
										BUF_SIZE,              	// maximum object size (low-order DWORD)
										szName);               	// name of mapping object
	// check for validity
	if (hMapFile == NULL)
	{
        // exit with error
		exit(-1);
	}//if

	// map the PLC variables
    plcvar = MapViewOfFile(	hMapFile,   						// handle to map object
                        	FILE_MAP_ALL_ACCESS, 				// read/write permission
							0,
							0,
							BUF_SIZE);

    // check for validity
    if (plcvar == NULL)
    {
    	// close the memory file
        CloseHandle(hMapFile);

        // exit with error
		exit(-2);
    }//if

    //---------------------------------------------------------------
    // initialize the PLC simulation functions
    //---------------------------------------------------------------

	// set the run flag
	app_is_running = TRUE;
	plcvar->ref_degisken=0;

	// clear the timer counters
	t1.QuadPart = 0;
	t2.QuadPart = 0;

	// initialize the clock system
	clock_init();

	// initialize the driver interface
	drvif_init(&my_drvif);

	// initialize the library interface
	libif_init(&my_libif);

	// call the PLC application entry point
	app_main(0);

	// call the PLC application initialize function
	app_init();

    // create the periodic timer event
    if ((plcTimer = timeSetEvent(1, 0, PLC_AppProc, 0, TIME_ONESHOT)) == 0)
    {
		// release the PLC memory
		UnmapViewOfFile(plcvar);

    	// close the memory file
        CloseHandle(hMapFile);

        // exit with error
		exit(-3);
    }//if

	// infinite loop to yield PLC application
	while (app_is_running)
	{
		// suspend the main loop
		Sleep(1000);
	}//while

	// kill the periodic timer
    timeKillEvent(plcTimer);

	// call the PLC application exit function
	app_exit();

	// release the PLC memory
	UnmapViewOfFile(plcvar);

	// close the memory file
    CloseHandle(hMapFile);

	return 0;
}//main
#endif //PLC_SIM


