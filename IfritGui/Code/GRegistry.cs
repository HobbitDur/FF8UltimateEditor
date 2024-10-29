using System;
using System.Reflection;
using System.Runtime.InteropServices;
using Microsoft.Win32;
using Microsoft.Win32.SafeHandles;


namespace Ifrit.Code
{
    static class GRegistry
    {

        [DllImport("advapi32.dll", CharSet = CharSet.Unicode, EntryPoint = "RegOpenKeyEx")]
        static extern int RegOpenKeyEx(IntPtr hKey, string subKey, uint options, int sam,
            out IntPtr phkResult);

        [Flags]
        public enum eRegWow64Options : int
        {
            /// <summary>
            /// No key.
            /// </summary>
            None = 0x0000,
            /// <summary>
            /// Indicates that an application on 64-bit Windows should operate on the 32-bit registry view.
            /// This flag must be combined using the OR operator with the other flags in this table that either query or access registry values.
            /// Windows 2000: This flag is not supported.
            /// </summary>
            KEY_WOW64_32KEY = 0x0200,
            /// <summary>
            /// Indicates that an application on 64-bit Windows should operate on the 64-bit registry view.
            /// This flag must be combined using the OR operator with the other flags in this table that either query or access registry values.
            /// Windows 2000: This flag is not supported.
            /// </summary>
            KEY_WOW64_64KEY = 0x0100,
            /// <summary>
            /// Combines the STANDARD_RIGHTS_REQUIRED, KEY_QUERY_VALUE, KEY_SET_VALUE, KEY_CREATE_SUB_KEY, KEY_ENUMERATE_SUB_KEYS, KEY_NOTIFY, and KEY_CREATE_LINK access rights.
            /// </summary>
            KEY_ALL_ACCESS = 0xF003F,
            /// <summary>
            /// Reserved for system use.
            /// </summary>
            KEY_CREATE_LINK = 0x0020,
            /// <summary>
            /// Required to create a subkey of a registry key.
            /// </summary>
            KEY_CREATE_SUB_KEY = 0x0004,
            /// <summary>
            /// Required to enumerate the subkeys of a registry key.
            /// </summary>
            KEY_ENUMERATE_SUB_KEYS = 0x0008,
            /// <summary>
            /// Equivalent to KEY_READ.
            /// </summary>
            KEY_EXECUTE = 0x20019,
            /// <summary>
            /// Required to request change notifications for a registry key or for subkeys of a registry key.
            /// </summary>
            KEY_NOTIFY = 0x0010,
            /// <summary>
            /// Required to query the values of a registry key.
            /// </summary>
            KEY_QUERY_VALUE = 0x0001,
            /// <summary>
            /// Combines the STANDARD_RIGHTS_READ, KEY_QUERY_VALUE, KEY_ENUMERATE_SUB_KEYS, and KEY_NOTIFY values.
            /// </summary>
            KEY_READ = 0x20019,
            /// <summary>
            /// Required to create, delete, or set a registry value.
            /// </summary>
            KEY_SET_VALUE = 0x0002,
            /// <summary>
            /// Combines the STANDARD_RIGHTS_WRITE, KEY_SET_VALUE, and KEY_CREATE_SUB_KEY access rights.
            /// </summary>
            KEY_WRITE = 0x20006,
        }

        [Flags]
        public enum eRegistryRights : int
        {
            ReadKey = 131097,
            WriteKey = 131078,
        }

        public static RegistryKey OpenSubKey(RegistryKey pParentKey, string pSubKeyName,
                                             bool pWriteable,
                                             eRegWow64Options pOptions)
        {
            if (pParentKey == null || GetRegistryKeyHandle(pParentKey).Equals(System.IntPtr.Zero))
                throw new System.Exception("OpenSubKey: Parent key is not open");

            eRegistryRights Rights = eRegistryRights.ReadKey;
            if (pWriteable)
                Rights = eRegistryRights.WriteKey;

            System.IntPtr SubKeyHandle;
            System.Int32 Result = RegOpenKeyEx(GetRegistryKeyHandle(pParentKey), pSubKeyName, 0,
                                              (int)Rights | (int)pOptions, out SubKeyHandle);
            if (Result != 0)
            {
                System.ComponentModel.Win32Exception W32ex =
                    new System.ComponentModel.Win32Exception();
                throw new System.Exception("OpenSubKey: Exception encountered opening key",
                    W32ex);
            }

            return PointerToRegistryKey(SubKeyHandle, pWriteable, false);
        }

        private static System.IntPtr GetRegistryKeyHandle(RegistryKey pRegisteryKey)
        {
            Type ty = Type.GetType("Microsoft.Win32.RegistryKey");
            FieldInfo Info = ty.GetField("hkey", BindingFlags.NonPublic | BindingFlags.Instance);

            SafeHandle Handle = (SafeHandle)Info.GetValue(pRegisteryKey);
            IntPtr RealHandle = Handle.DangerousGetHandle();

            return Handle.DangerousGetHandle();
        }

        private static RegistryKey PointerToRegistryKey(IntPtr hKey, bool pWritable,
            bool pOwnsHandle)
        {
            // Create a SafeHandles.SafeRegistryHandle from this pointer - this is a private class
            BindingFlags privateConstructors = BindingFlags.Instance | BindingFlags.NonPublic;
            Type safeRegistryHandleType = typeof(
                SafeHandleZeroOrMinusOneIsInvalid).Assembly.GetType(
                "Microsoft.Win32.SafeHandles.SafeRegistryHandle");

            Type[] safeRegistryHandleConstructorTypes = new Type[] { typeof(System.IntPtr),
        typeof(System.Boolean) };
            ConstructorInfo safeRegistryHandleConstructor =
                safeRegistryHandleType.GetConstructor(privateConstructors,
                null, safeRegistryHandleConstructorTypes, null);
            Object safeHandle = safeRegistryHandleConstructor.Invoke(new Object[] { hKey,
        pOwnsHandle });

            // Create a new Registry key using the private constructor using the
            // safeHandle - this should then behave like 
            // a .NET natively opened handle and disposed of correctly
            Type registryKeyType = typeof(Microsoft.Win32.RegistryKey);
            Type[] registryKeyConstructorTypes = new Type[] { safeRegistryHandleType,
        typeof(Boolean) };
            ConstructorInfo registryKeyConstructor =
                registryKeyType.GetConstructor(privateConstructors, null,
                registryKeyConstructorTypes, null);
            RegistryKey result = (RegistryKey)registryKeyConstructor.Invoke(new Object[] {
        safeHandle, pWritable });
            return result;
        }

        public static void SetRegValue(RegistryKey regKey, string name, object value, RegistryValueKind regKind)
        {
            if (regKey == null)
                return;
            regKey.SetValue(name, value, regKind);
        }

        public static object GetRegValue(RegistryKey regKey, string name, object nullValueReturned)
        {
            if (regKey == null)
				return nullValueReturned;
			if (regKey.GetValue(name) == null)
                return nullValueReturned;
            return regKey.GetValue(name);
        }
    }
}
