// SPDX-License-Identifier: GPL-2.0
#include <linux/dmi.h>
#include <linux/init.h>
#include <linux/module.h>
#include <linux/platform_data/x86/asus-wmi.h>

static int __init t305ca_als_init(void)
{
	u32 result = 0;
	int err;

	if (!dmi_match(DMI_PRODUCT_NAME, "T305CA"))
		return -ENODEV;

	err = asus_wmi_set_devstate(ASUS_WMI_DEVID_ALS_ENABLE, 1, &result);
	if (err)
		return err;
	if (result != 1)
		return -EIO;

	pr_info("t305ca-als: ambient light sensor enabled\n");
	return 0;
}

static void __exit t305ca_als_exit(void)
{
	u32 result = 0;
	int err;

	err = asus_wmi_set_devstate(ASUS_WMI_DEVID_ALS_ENABLE, 0, &result);
	if (err || result != 1)
		pr_warn("t305ca-als: could not disable ambient light sensor\n");
}

module_init(t305ca_als_init);
module_exit(t305ca_als_exit);
MODULE_DESCRIPTION("Enable the ASUS T305CA ambient light sensor");
MODULE_LICENSE("GPL");
MODULE_IMPORT_NS("ASUS_WMI");
