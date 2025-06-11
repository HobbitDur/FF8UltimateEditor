using System;
using System.Collections;
using System.Collections.Generic;
using System.Text;
using System.IO;
using Ifrit.Compression;

namespace Ifrit.Code
{

    public struct BattleFileInfo
    {
        public uint unpackedFileLength;
        public uint fileStartOffset;
        public bool compressed;
        public bool changed;
        internal void ChangeUnpackedLength(byte[] decodedBuffer)
        {
            unpackedFileLength = (uint)decodedBuffer.Length;
            //if(!compressed) return;
            //using(MemoryStream stream =new MemoryStream(encodedBuffer, 0, encodedBuffer.Length, true))
            //{
            //    unpackedFileLength = (uint)LZSS.Decode(stream).Length;
            //}            
        }

        internal void SetFStart(uint p)
        {
            fileStartOffset = p;
        }
    }

    public struct BattleFile
    {
        public byte[] Data { get; set; }
        public BattleFileInfo Info { get; set; }
        public string Name { get; set; }
    }

    public sealed class BattleFileHandler : Object
    {

        #region Constants

        const int UNPACKED_LENGTH_OFFSET = 0;
        const int LOCATION_OFFSET = 4;
        const int LZS_OFFSET = 8;
        const int BFI_INC = 12;
        const int DEFAULT_FILE_COUNT = 853;

        const string DEFAULT_INTERNAL_PATH = "c:\\ff8\\data\\eng\\battle\\";
        const string BATTLE_FS = "battle.fs";
        const string BATTLE_FL = "battle.fl";
        const string BATTLE_FI = "battle.fi";
        public const string UNPACK_LOC = "Battle Files";
        #endregion

        #region Attributes and Variables

        public int PackedFiles;

        private string battlePath;

        private string[] simpleNames;

        public string[] FileNames
        {
            get
            {
                if (AllFilesExists) return simpleNames;
                return null;
            }
        }

        /// <summary>
        /// Gets or Sets the path to battle.f* files, NOT including filename. i.e: "c:/ff8/data/". Must end with a folder seperator.
        /// </summary>
        public string BattlePath 
        { 
            get 
            { 
                if(string.IsNullOrEmpty(battlePath)) return string.Empty;
                AddDirSeperator(ref battlePath);
                return battlePath; 
            } 
            set { Setup(value); } 
        }

        private string internalPath;

        /// <summary>
        /// Gets all fileNames in battle.fl including the internal path. Example: c:\ff8\data\eng\battle\file1.x.
        /// </summary>
        public string[] InternalPaths
        {
            get
            {
                if(string.IsNullOrEmpty(BattlePath)) return null;
                string file = BattlePath + BATTLE_FL;
                if(!File.Exists(file)) return(null);
                return File.ReadAllLines(file, Encoding.ASCII);
            }
        }

        /// <summary>
        /// Gets wheter all expected files are present in path contained by 'BattlePath'.
        /// </summary>
        private bool AllFilesExists
        { 
            get 
            {
                if (string.IsNullOrEmpty(BattlePath)) return false;
                return (File.Exists(BattlePath + BATTLE_FS) &
                        File.Exists(BattlePath + BATTLE_FI) &
                        File.Exists(BattlePath + BATTLE_FL)); 
            } 
        }

        /// <summary>
        /// Gets all the valid battle files in the battle.fs decompressed.
        /// </summary>
        public BattleFile[] FSFiles
        {
            get
            {
                if(!AllFilesExists) return null;

                if(simpleNames == null) return null;

                byte[] fiFile = File.ReadAllBytes(BattlePath + BATTLE_FI);

                if (fiFile.Length < simpleNames.Length * BFI_INC) 
                    return null;

                FileStream fs = new FileStream(BattlePath + BATTLE_FS, FileMode.Open, FileAccess.Read);

                BattleFile[] files = new BattleFile[simpleNames.Length];
                int i = -1, fiOffset = 0;

                foreach (string s in simpleNames)
                {
                    i++;
                    BattleFileInfo inf = new BattleFileInfo();
                    inf.compressed = BitConverter.ToBoolean(fiFile, fiOffset + LZS_OFFSET);
                    inf.unpackedFileLength = BitConverter.ToUInt32(fiFile, fiOffset + UNPACKED_LENGTH_OFFSET);
                    inf.fileStartOffset = BitConverter.ToUInt32(fiFile, fiOffset + LOCATION_OFFSET);
                    inf.changed = false;

                    files[i] = new BattleFile();
                    files[i].Name = s;                    

                    uint end = 0; int count = 1;
                    do
                    {
                        int offset = fiOffset + LOCATION_OFFSET + (BFI_INC * count);
                            end = offset > fiFile.Length - 1 ? (uint)fs.Length : BitConverter.ToUInt32(fiFile, offset);
                        if(end == 0) count++;
                    }
                    while(end == 0);

                    SetBFData(ref inf, ref files[i], end, fs, true);
                    fiOffset += BFI_INC;
                }

                GC.Collect(); GC.WaitForPendingFinalizers();
                return files;
            }
        }

        #endregion

        #region Constructors, Setup and Indexers

        public BattleFileHandler() { Setup(null); }
        public BattleFileHandler(string path) { Setup(path); }

        private void Setup(string path)
        {
            battlePath = path;
            PackedFiles = 0;
            if (AllFilesExists)
            {
                simpleNames = GetFileNames(BattlePath + BATTLE_FL, true);
                string s = InternalPaths[0];
                internalPath = s.Remove(s.LastIndexOf('\\') + 1);
            }
            else
            {
                simpleNames = null;
                internalPath = DEFAULT_INTERNAL_PATH;
            }
            internalPath.ToString();
        }

        public BattleFile this[int index]
        {
            get
            {
                if (!AllFilesExists)
                    throw new Exception("Class not properly initiated.");
                return GetBattleFile(index);
            }
        }

        public BattleFile this[string name]
        {
            get
            {
                if (!AllFilesExists)
                    throw new Exception("Class not properly initiated.");
                return GetBattleFile(name);
            }
        }

        #endregion

        #region Extract

        #region Multiple

        public bool ExtractBattleFiles()
        {
            if (string.IsNullOrEmpty(BattlePath)) return false;
            return ExtractBattleFiles(BattlePath + UNPACK_LOC + Path.DirectorySeparatorChar);
        }

        public bool ExtractBattleFiles(string destDir)
        {
            if (!AllFilesExists) return false;
            return ExtractBattleFiles(FSFiles, destDir);
        }

        public static bool ExtractBattleFiles(BattleFile[] files, string destDir)
        {
            try
            {
                //AddDirSeperator(ref destDir);
                if (!Directory.Exists(destDir)) Directory.CreateDirectory(destDir);
                foreach (BattleFile file in files)
                {
                    //if(!string.IsNullOrEmpty(file.Name) && file.Data != null)
                        File.WriteAllBytes(destDir + file.Name, file.Data);
                }
            }
            catch (IOException iex)
            {
                #if DEBUG
                Console.WriteLine(iex.Message);
                #endif
                return false;
            }
            catch (Exception ex)
            {
                #if DEBUG
                Console.WriteLine(ex.Message);
                #endif
                return false;
            }
            return true;
        }

        #endregion

        #region Single

        public bool ExtractBattleFile(int index)
        {
            BattleFile file = this[index];
            return ExtractBattleFile(file, BattlePath + UNPACK_LOC + Path.DirectorySeparatorChar);
        }

        public bool ExtractBattleFile(string name)
        {
            BattleFile file = this[name];
            return ExtractBattleFile(file, BattlePath + UNPACK_LOC + Path.DirectorySeparatorChar);
        }

        public bool ExtractBattleFile(string destDir, int index)
        {
            return ExtractBattleFile(BattlePath, destDir, index, false, simpleNames[index]);
        }

        public static bool ExtractBattleFile(string sourceDir, string destDir, int index)
        {
            return ExtractBattleFile(sourceDir, destDir, index, true, null);
        }

        private static bool ExtractBattleFile(string sourceDir, string destDir, int index, bool check, string name)
        {
            BattleFile file = GetBattleFile(index, sourceDir, check, name, true);
            return ExtractBattleFile(file, destDir);
        }

        public bool ExtractBattleFile(string destDir, string name)
        {
            return ExtractBattleFile(BattlePath, destDir, name, false, simpleNames);
        }

        public static bool ExtractBattleFile(string sourceDir, string destDir, string name)
        {
            return ExtractBattleFile(sourceDir, destDir, name, true, null);
        }

        private static bool ExtractBattleFile(string sourceDir, string destDir, string name, bool check, string[] names)
        {
            BattleFile file = GetBattleFile(name, sourceDir, check, names);
            return ExtractBattleFile(file, destDir);
        }

        public static bool ExtractBattleFile(BattleFile file)
        {
            string path = Directory.GetDirectoryRoot(AppDomain.CurrentDomain.BaseDirectory);
            return ExtractBattleFile(file, path);
        }

        public static bool ExtractBattleFile(BattleFile file, string dest)
        {
            try
            {
                AddDirSeperator(ref dest);
                if (!Directory.Exists(dest)) Directory.CreateDirectory(dest);
                File.WriteAllBytes(dest + file.Name, file.Data);
            }
            catch (IOException iex)
            {
                #if DEBUG
                Console.Write(iex.Message);
                #endif
                return false;
            }
            catch (Exception ex)
            {
                #if DEBUG
                Console.Write(ex.Message);
                #endif
                return false;
            }
            return true;
        }

        #endregion

        #endregion

        #region Pack

        public bool PackBattleFiles()
        {
            return PackBattleFiles(BattlePath + UNPACK_LOC + Path.DirectorySeparatorChar);
        }

        public bool PackBattleFiles(string sourceDir)
        {
            if (!AllFilesExists) return false;
            PackedFiles = 0;
            return PackBattleFiles(sourceDir, BattlePath, false, internalPath, ref PackedFiles);
        }

        public static bool PackBattleFiles(string sourceDir, string destDir)
        {
            int i = 0;
            return PackBattleFiles(sourceDir, destDir, true, null, ref i);
        }

        public static bool PackBattleFiles(string sourceDir, string destDir, ref int i)
        {
            return PackBattleFiles(sourceDir, destDir, true, null, ref i);
        }

        private static bool PackBattleFiles(string sourceDir, string destDir, bool Check, string internalPath, ref int filesPacked)
        {
            if (Check)
            {
                if (!Directory.Exists(sourceDir))
                    throw new ArgumentException("Source folder does not exist", "source");
                if (!Directory.Exists(destDir)) Directory.CreateDirectory(destDir);
                AddDirSeperator(ref destDir);
            }
            AddDirSeperator(ref sourceDir);

            int nrOfFiles = 0;
            List<string> pnames = new List<string>();
            foreach (string bf in DefaultNames())
            {
                if(File.Exists(sourceDir + bf))
                {
                    pnames.Add(bf); nrOfFiles++;
                }
                else
                    pnames.Add(string.Empty);
            }
            GC.Collect(); GC.WaitForPendingFinalizers();

            bool allF = Check ? (File.Exists(destDir + BATTLE_FS) & File.Exists(destDir + BATTLE_FI) & File.Exists(destDir + BATTLE_FL)) : true;

            if (!allF && nrOfFiles < DEFAULT_FILE_COUNT)
                throw new Exception("If you pack files from a folder with less battle files than expected (" + DEFAULT_FILE_COUNT + "), all battle archives (battle.fs, battle.fl and battle.fi) must be present in destination folder." + Environment.NewLine + "The pack process assumes default names; do not re-name battle files.");

            if (string.IsNullOrEmpty(internalPath))
            {
                if (allF)
                {
                    string s = GetFileNames(destDir + BATTLE_FL, false)[0];
                    internalPath = s.Remove(s.LastIndexOf(Path.DirectorySeparatorChar) + 1);
                }
                else if (!File.Exists(destDir + BATTLE_FI))
                    throw new Exception("battle.fi must be present.");
                else
                    internalPath = DEFAULT_INTERNAL_PATH;
            }
                

            FileStream f = new FileStream(destDir + BATTLE_FS + ".temp", FileMode.Create, FileAccess.Write);
            f.Close(); f = new FileStream(destDir + BATTLE_FI + ".temp", FileMode.Create, FileAccess.Write);
            f.Close(); f = new FileStream(destDir + BATTLE_FL + ".temp", FileMode.Create, FileAccess.Write);
            f.Close(); f.Dispose(); GC.Collect(); GC.WaitForPendingFinalizers();

            BattleFile file; int filePos = 0, count = 0; bool decompressed;
            foreach (string s in pnames)
            {
                //Get file from source folder if it exsist.                
                if (!string.IsNullOrEmpty(s))
                {
                    file = GetDefaultBattleFile(sourceDir + s);
                    decompressed = true;
                }
                //Get file from battle.fs if not present in source folder
                else
                {
                    file = GetBattleFile(count, destDir, Check, s, false);
                    decompressed = false;
                }
                AppendBattleFile(destDir, file, internalPath, ref filePos, decompressed);
                filesPacked++; count++;
            }
            
            File.Copy(destDir + BATTLE_FS + ".temp", destDir + BATTLE_FS, true);
            File.Copy(destDir + BATTLE_FI + ".temp", destDir + BATTLE_FI, true);
            File.Copy(destDir + BATTLE_FL + ".temp", destDir + BATTLE_FL, true);
            File.Delete(destDir + BATTLE_FS + ".temp"); 
            File.Delete(destDir + BATTLE_FI + ".temp"); 
            File.Delete(destDir + BATTLE_FL + ".temp");

            return true;
        }

        public BattleFile DeComp()
        {
            BattleFile f = GetBattleFile(1, BattlePath, false, null, true);
            //EncodeBattleFile(ref f);
            return f;
        }

        public BattleFile NoDeComp()
        {
            BattleFile f = GetBattleFile(1, BattlePath, false, null, false);
            //BattleFileInfo i = f.Info;
            //using(MemoryStream stream = new MemoryStream(f.Data, true))
            //{
            //    f.Data = LZSS.Decode(stream, 4);
            //    stream.Close();
            //}
            //EncodeBattleFile(ref f);
            return f;
        }

        private static bool AppendBattleFile(string destDir, BattleFile file, string internalFLPath, ref int filePos, bool decompressed)
        {

            //int fslength = 0;
            if (file.Info.compressed && decompressed)
            {
                //if(decompressed)
                    EncodeBattleFile(ref file);
                //fslength += 4;
            }
            //fslength += file.Data.Length;

            FileStream f = new FileStream(destDir + BATTLE_FI + ".temp", FileMode.Append, FileAccess.Write);
            

            //DRY
            foreach (byte b in BitConverter.GetBytes(file.Info.unpackedFileLength))
                f.WriteByte(b);
            foreach (byte b in BitConverter.GetBytes((uint)(file.Info.unpackedFileLength > 0 ? filePos : 0)))
                f.WriteByte(b);
            foreach (byte b in BitConverter.GetBytes(Convert.ToUInt32(file.Info.compressed)))
                f.WriteByte(b);
            //Remembers to update file position.
            filePos += file.Data.Length;

            f.Flush(); f.Close();
            f = new FileStream(destDir + BATTLE_FS + ".temp", FileMode.Append, FileAccess.Write);
            if (file.Info.compressed)
            {
                filePos += 4;
                foreach (byte b in BitConverter.GetBytes(file.Data.Length))
                    f.WriteByte(b);
            }
            foreach(byte b in file.Data)
                f.WriteByte(b);

            f.Flush(); f.Close();

            f = new FileStream(destDir + BATTLE_FL + ".temp", FileMode.Append, FileAccess.Write);
            foreach(char c in internalFLPath + file.Name)
                f.WriteByte(Convert.ToByte(c));
            f.WriteByte(0xD); f.WriteByte(0xA);

            f.Flush(); f.Close(); f.Dispose();
            GC.Collect(); GC.WaitForPendingFinalizers();

            return true;
        }

        /// <summary>
        /// Pack battle files into default FF8 data directory.
        /// </summary>
        /// <param name="files">Files to pack.</param>
        /// <returns>True if success.</returns>
        public bool PackBattleFiles(BattleFile[] files)
        {
            if (string.IsNullOrEmpty(BattlePath)) return false;
            //string path = Directory.GetDirectoryRoot(AppDomain.CurrentDomain.BaseDirectory);
            return PackBattleFiles(files, BattlePath);
        }

        public static bool PackBattleFiles(BattleFile[] files, string path)
        {
            //if(!Manageable) return false;
            if(files == null) return false;

            StringBuilder sb = new StringBuilder();
            MemoryStream stream = null;

            AddDirSeperator(ref path);
            string fsPath = path + BATTLE_FS;
            string flPath = path + BATTLE_FL;
            string fiPath = path + BATTLE_FI;

            int fileLength = 0, findex = 0; uint[] filePos = new uint[files.Length];
            //Encode files if needed.
            for(int i = 0; i < files.Length; i++, findex++)
            {
                if(files[i].Data != null)
                {
                    if(files[i].Info.compressed)
                    {
                        EncodeBattleFile(ref files[i]);
                        fileLength += files[i].Data.Length + 4;
                    }
                    else
                        fileLength += files[i].Data.Length;
                }
                else if (File.Exists(flPath) && File.Exists(fiPath) && File.Exists(fsPath))
                {
                    files[i] = GetBattleFile(findex, path, false, files[i].Name, false);
                    fileLength += files[i].Data.Length;
                }
                else
                    throw new ArgumentException("If a file is empty, valid battle files must be present to get a valid pack.", "path");
                if (i > 0)
                {
                    filePos[i] = (uint)(files[i].Info.unpackedFileLength > 0 ? files[i - 1].Data.Length : 0);
                    if (files[i].Info.compressed) filePos[i] += 4;
                }
            }

            if(stream != null) { stream.Close(); stream.Dispose(); }
            GC.Collect(); GC.WaitForPendingFinalizers();

            if(fileLength > 0)
            {

                //Write Battle FS
                //if(File.Exists(fsPath)) File.Delete(fsPath);
                FileStream fs = File.Create(fsPath, fileLength);

                byte[] battle_fs = new byte[fileLength];
                for(int i = 0; i < files.Length; i++)
                {
                    if(files[i].Info.compressed)
                        foreach(byte b in BitConverter.GetBytes(files[i].Data.Length))
                            fs.WriteByte(b);
                    fs.Write(files[i].Data, 0, files[i].Data.Length);
                } 
                fs.Flush(); fs.Close();
                //GC.Collect(); GC.WaitForPendingFinalizers();

                //Write Battle FL
                fileLength = 0;
                string[] names = new string[files.Length];

                for(int i = 0; i < names.Length; i++)
                {
                    if(names[i].Contains("" + Path.DirectorySeparatorChar) &&
                       !names[i].EndsWith("" + Path.DirectorySeparatorChar))
                        names[i] = names[i].Remove(names[i].LastIndexOf(Path.DirectorySeparatorChar) + 1);
                    names[i] += files[i].Name;
                    fileLength += names[i].Length + 2;
                }

                //if(File.Exists(flPath)) File.Delete(flPath);
                fs = File.Create(flPath, fileLength);

                foreach(string s in names)
                {
                    foreach(char c in s)
                        fs.WriteByte(Convert.ToByte(c));
                    fs.WriteByte(0xD); fs.WriteByte(0xA);
                }
                fs.Flush(); fs.Close();
                //GC.Collect(); GC.WaitForPendingFinalizers();

                //Write Battle FS
                fileLength = BFI_INC * files.Length;
                //if(File.Exists(fiPath)) File.Delete(fiPath);
                fs = File.Create(fiPath, fileLength);

                uint fp = 0; //to track file positions
                for(int i = 0; i < files.Length; i++)
                {
                    fp += filePos[i];
                    foreach(byte b in BitConverter.GetBytes(files[i].Info.unpackedFileLength))
                        fs.WriteByte(b);
                    foreach(byte b in BitConverter.GetBytes(fp)) //files[i].Info.fileStartOffset))
                        fs.WriteByte(b);
                    foreach(byte b in BitConverter.GetBytes(Convert.ToInt32(files[i].Info.compressed)))
                        fs.WriteByte(b);
                }
                fs.Flush(); fs.Close();
                GC.Collect(); GC.WaitForPendingFinalizers();
            }
            else return false;

            return true;
        }

        #endregion

        #region Default and other Static

        public static int NumberOfFiles(string battleFL)
        {
            if (!File.Exists(battleFL) || !battleFL.EndsWith(BATTLE_FL)) return -1;
            return GetFileNames(battleFL, false).Length;
        }

        public static string[] GetFileNames(string battleFL, bool trim)
        {
            if (!File.Exists(battleFL) || !battleFL.EndsWith(BATTLE_FL)) return null;
            string[] names = File.ReadAllLines(battleFL, Encoding.ASCII);
            if (trim)
                for (int i = 0; i < names.Length; i++)
                    TrimFolders(ref names[i]);
            return names;
        }


        public static int NrOfDefaultFiles(string sourceDir)
        {
            int nrOfFiles = 0;

            foreach (string bf in DefaultNames())
            {
                if (File.Exists(sourceDir + bf))
                    nrOfFiles++;
            }

            return nrOfFiles;
        }

        public static string[] DefaultNames()
        {
            return new string[] 
            {
                "a0stg012.x","a8def.tim","a9btlfnt.bft","b0wave.dat","c0m015.dat","c0m051.dat","c0m095.dat","c0m096.dat","d0c000.dat","d0w000.dat","d3c007.dat","d3w018.dat","mag005_b.02","mag005_b.03","mag005_b.04","mag005_b.05","mag005_b.06","mag005_b.07","mag005_b.08","mag005_b.09","mag005_b.10",
                "mag005_b.11","mag005_b.12","mag005_b.13","mag005_b.14","mag005_b.15","mag005_b.16","mag005_b.17","mag046_b.1t0","mag046_b.1t1","mag046_b.1t2","mag161_a.dat","mag163_a.dat","mag163_b.dat","mag164_a.dat","mag164_b.dat","mag164_c.dat","mag184_d.dat","mag184_e.dat","mag184_f.dat","mag184_g.dat",
                "mag184_h.dat","mag184_i.dat","mag200_b.02","mag200_b.03","mag200_b.04","mag200_b.05","mag200_b.06","mag200_b.07","mag200_b.08","mag200_b.09","mag200_b.10","mag200_b.11","mag200_b.12","mag290_h.00","mag290_h.01","mag290_h.02","mag290_h.03","mag290_h.04","mag290_h.05","mag290_h.06",
                "mag290_h.07","mag290_h.t00","r0win.dat","scene.out","ma8def_0.tim","ma8def_1.tim","ma8def_2.tim","ma8def_p.0","ma8def_p.1","ma8def_p.2","ma8def_p.3","a0stg000.x","a0stg001.x","a0stg002.x","a0stg003.x","a0stg004.x","a0stg005.x","a0stg006.x","a0stg007.x","a0stg008.x",
                "a0stg009.x","a0stg010.x","a0stg011.x","a0stg013.x","a0stg014.x","a0stg015.x","a0stg016.x","a0stg017.x","a0stg018.x","a0stg019.x","a0stg020.x","a0stg021.x","a0stg022.x","a0stg023.x","a0stg024.x","a0stg025.x","a0stg026.x","a0stg027.x","a0stg028.x","a0stg029.x",
                "a0stg030.x","a0stg031.x","a0stg032.x","a0stg033.x","a0stg034.x","a0stg035.x","a0stg036.x","a0stg037.x","a0stg038.x","a0stg039.x","a0stg040.x","a0stg041.x","a0stg042.x","a0stg043.x","a0stg044.x","a0stg045.x","a0stg046.x","a0stg047.x","a0stg048.x","a0stg049.x",
                "a0stg050.x","a0stg051.x","a0stg052.x","a0stg053.x","a0stg054.x","a0stg055.x","a0stg056.x","a0stg057.x","a0stg058.x","a0stg059.x","a0stg060.x","a0stg061.x","a0stg062.x","a0stg063.x","a0stg064.x","a0stg065.x","a0stg066.x","a0stg067.x","a0stg068.x","a0stg069.x",
                "a0stg070.x","a0stg071.x","a0stg072.x","a0stg073.x","a0stg074.x","a0stg075.x","a0stg076.x","a0stg077.x","a0stg078.x","a0stg079.x","a0stg080.x","a0stg081.x","a0stg082.x","a0stg083.x","a0stg084.x","a0stg085.x","a0stg086.x","a0stg087.x","a0stg088.x","a0stg089.x",
                "a0stg090.x","a0stg091.x","a0stg092.x","a0stg093.x","a0stg094.x","a0stg095.x","a0stg096.x","a0stg097.x","a0stg098.x","a0stg099.x","a0stg100.x","a0stg101.x","a0stg102.x","a0stg103.x","a0stg104.x","a0stg105.x","a0stg106.x","a0stg107.x","a0stg108.x","a0stg109.x",
                "a0stg110.x","a0stg111.x","a0stg112.x","a0stg113.x","a0stg114.x","a0stg115.x","a0stg116.x","a0stg117.x","a0stg118.x","a0stg119.x","a0stg120.x","a0stg121.x","a0stg122.x","a0stg123.x","a0stg124.x","a0stg125.x","a0stg126.x","a0stg127.x","a0stg128.x","a0stg129.x",
                "a0stg130.x","a0stg131.x","a0stg132.x","a0stg133.x","a0stg134.x","a0stg135.x","a0stg136.x","a0stg137.x","a0stg138.x","a0stg139.x","a0stg140.x","a0stg141.x","a0stg142.x","a0stg143.x","a0stg144.x","a0stg145.x","a0stg146.x","a0stg147.x","a0stg148.x","a0stg149.x",
                "a0stg150.x","a0stg151.x","a0stg152.x","a0stg153.x","a0stg154.x","a0stg155.x","a0stg156.x","a0stg157.x","a0stg158.x","a0stg159.x","a0stg160.x","a0stg161.x","a0stg162.x","c0m000.dat","c0m001.dat","c0m002.dat","c0m003.dat","c0m004.dat","c0m005.dat","c0m006.dat",
                "c0m007.dat","c0m008.dat","c0m009.dat","c0m010.dat","c0m011.dat","c0m012.dat","c0m013.dat","c0m014.dat","c0m016.dat","c0m017.dat","c0m018.dat","c0m019.dat","c0m020.dat","c0m021.dat","c0m022.dat","c0m023.dat","c0m024.dat","c0m025.dat","c0m026.dat","c0m027.dat",
                "c0m028.dat","c0m029.dat","c0m030.dat","c0m031.dat","c0m032.dat","c0m033.dat","c0m034.dat","c0m035.dat","c0m036.dat","c0m037.dat","c0m038.dat","c0m039.dat","c0m040.dat","c0m041.dat","c0m042.dat","c0m043.dat","c0m044.dat","c0m045.dat","c0m046.dat","c0m047.dat",
                "c0m048.dat","c0m049.dat","c0m050.dat","c0m052.dat","c0m053.dat","c0m054.dat","c0m055.dat","c0m056.dat","c0m057.dat","c0m058.dat","c0m059.dat","c0m060.dat","c0m061.dat","c0m062.dat","c0m063.dat","c0m064.dat","c0m065.dat","c0m066.dat","c0m067.dat","c0m068.dat",
                "c0m069.dat","c0m070.dat","c0m071.dat","c0m072.dat","c0m073.dat","c0m074.dat","c0m075.dat","c0m076.dat","c0m077.dat","c0m078.dat","c0m079.dat","c0m080.dat","c0m081.dat","c0m082.dat","c0m083.dat","c0m084.dat","c0m085.dat","c0m086.dat","c0m087.dat","c0m088.dat",
                "c0m089.dat","c0m090.dat","c0m091.dat","c0m092.dat","c0m093.dat","c0m094.dat","c0m097.dat","c0m098.dat","c0m099.dat","c0m100.dat","c0m101.dat","c0m102.dat","c0m103.dat","c0m104.dat","c0m105.dat","c0m106.dat","c0m107.dat","c0m108.dat","c0m109.dat","c0m110.dat",
                "c0m111.dat","c0m112.dat","c0m113.dat","c0m114.dat","c0m115.dat","c0m116.dat","c0m117.dat","c0m118.dat","c0m119.dat","c0m120.dat","c0m121.dat","c0m122.dat","c0m123.dat","c0m124.dat","c0m125.dat","c0m126.dat","c0m127.dat","c0m128.dat","c0m129.dat","c0m130.dat",
                "c0m131.dat","c0m132.dat","c0m133.dat","c0m134.dat","c0m135.dat","c0m136.dat","c0m137.dat","c0m138.dat","c0m139.dat","c0m140.dat","c0m141.dat","c0m142.dat","c0m143.dat","c0m144.dat","c0m145.dat","c0m146.dat","c0m147.dat","c0m148.dat","c0m149.dat","c0m150.dat",
                "c0m151.dat","c0m152.dat","c0m153.dat","c0m154.dat","c0m155.dat","c0m156.dat","c0m157.dat","c0m158.dat","c0m159.dat","c0m160.dat","c0m161.dat","c0m162.dat","c0m163.dat","c0m164.dat","c0m165.dat","c0m166.dat","c0m167.dat","c0m168.dat","c0m169.dat","c0m170.dat",
                "c0m171.dat","c0m172.dat","c0m173.dat","c0m174.dat","c0m175.dat","c0m176.dat","c0m177.dat","c0m178.dat","c0m179.dat","c0m180.dat","c0m181.dat","c0m182.dat","c0m183.dat","c0m184.dat","c0m185.dat","c0m186.dat","c0m187.dat","c0m188.dat","c0m189.dat","c0m190.dat",
                "c0m191.dat","c0m192.dat","c0m193.dat","c0m194.dat","c0m195.dat","c0m196.dat","c0m197.dat","c0m198.dat","c0m199.dat","d0c001.dat","d0w001.dat","d0w002.dat","d0w003.dat","d0w004.dat","d0w005.dat","d0w006.dat","d0w007.dat","d1c003.dat","d1c004.dat","d1w008.dat",
                "d1w009.dat","d1w010.dat","d1w011.dat","d2c006.dat","d2w013.dat","d2w014.dat","d2w015.dat","d2w016.dat","d3w019.dat","d3w020.dat","d3w021.dat","d4c009.dat","d4w023.dat","d4w024.dat","d4w025.dat","d4w026.dat","d4w027.dat","d5c011.dat","d5c012.dat","d5w028.dat",
                "d5w029.dat","d5w030.dat","d5w031.dat","d6c014.dat","d6w033.dat","d7c016.dat","d8c017.dat","d8c018.dat","d8w035.dat","d9c019.dat","d9c020.dat","d9w037.dat","dac021.dat","dac022.dat","daw039.dat","mag007_b.1s0","mag007_b.1s1","mag007_b.1s2","mag007_b.1t0","mag007_b.1t1",
                "mag064_h.00","mag064_h.01","mag064_h.02","mag064_h.03","mag076_b.02","mag076_b.03","mag076_b.04","mag076_b.05","mag078_b.1s0","mag078_b.1s1","mag078_b.1s2","mag078_b.1s3","mag078_b.1t0","mag078_b.9m0","mag084_b.1t0","mag084_b.1t1","mag084_b.1t2","mag085_b.1t0","mag085_b.1t1","mag086_b.1s0",
                "mag086_b.1t0","mag086_b.1t1","mag087_b.1p0","mag087_b.1r0","mag087_b.1r1","mag087_b.1s0","mag087_b.1t0","mag087_b.1t1","mag088_b.1s0","mag088_b.1s1","mag088_b.1t0","mag088_b.1t1","mag088_b.2p0","mag088_b.2p1","mag088_b.2s0","mag088_b.2s1","mag088_b.2t0","mag088_b.2t1","mag089_b.1t0","mag089_b.1z0",
                "mag094_b.1s0","mag094_b.1t0","mag094_b.1t1","mag094_b.1t2","mag094_b.1t3","mag094_b.1t4","mag094_b.1t5","mag094_b.2e0","mag094_b.2p0","mag094_b.2r0","mag094_b.2r1","mag094_b.2s0","mag094_b.2s1","mag094_b.2s2","mag094_b.2s3","mag094_b.2z0","mag094_b.3p0","mag094_b.3s0","mag094_b.3t0","mag094_b.3t1",
                "mag095_b.1t0","mag095_b.1t1","mag095_b.1t2","mag095_b.1t3","mag096_b.1t0","mag096_b.1t1","mag096_b.1t2","mag096_b.2s0","mag096_b.2t0","mag096_b.2t1","mag096_b.3p0","mag096_b.3s0","mag096_b.3s1","mag096_b.3t0","mag096_b.3t1","mag096_b.3t2","mag097_b.1t0","mag097_b.1t1","mag097_b.1t2","mag097_b.2s0",
                "mag097_b.2t0","mag097_b.2t1","mag097_b.3p0","mag097_b.3s0","mag097_b.3s1","mag097_b.3s2","mag097_b.3t0","mag097_b.3t1","mag097_b.3t2","mag097_b.3t3","mag098_b.1t0","mag098_b.1t1","mag098_b.1t2","mag098_b.2s0","mag098_b.2t0","mag098_b.2t1","mag098_b.3s0","mag098_b.3s1","mag098_b.3s2","mag098_b.3t0",
                "mag098_b.3t1","mag098_b.4p0","mag098_b.4r0","mag098_b.4r1","mag098_b.4s0","mag098_b.4s1","mag098_b.4s2","mag098_b.4t0","mag098_b.4t1","mag098_b.4t2","mag098_b.4t3","mag099_b.1t0","mag099_b.1t1","mag099_b.1t2","mag099_b.2s0","mag099_b.2t0","mag099_b.2t1","mag099_b.3p0","mag099_b.3s0","mag099_b.3t0",
                "mag099_b.4e0","mag099_b.4t0","mag099_b.4t1","mag099_b.5p0","mag099_b.5s0","mag099_b.5t0","mag099_b.5t1","mag115_h.00","mag115_h.01","mag115_h.02","mag115_h.03","mag115_h.04","mag115_h.05","mag115_h.06","mag115_h.07","mag115_h.08","mag115_h.09","mag115_h.10","mag115_h.11","mag115_h.12",
                "mag115_h.13","mag115_h.14","mag115_h.15","mag115_h.16","mag115_h.17","mag115_h.18","mag115_h.19","mag115_h.20","mag115_h.21","mag115_h.22","mag139_h.00","mag139_h.01","mag139_h.02","mag139_h.03","mag139_h.04","mag139_h.05","mag139_h.06","mag139_h.07","mag139_h.08","mag186_a.dat",
                "mag186_b.dat","mag186_c.dat","mag186_d.dat","mag186_e.dat","mag186_f.dat","mag186_g.dat","mag190_a.dat","mag190_b.dat","mag190_c.dat","mag190_d.dat","mag190_e.dat","mag190_f.dat","mag190_g.dat","mag199_a.dat","mag199_b.dat","mag199_c.dat","mag201_b.02","mag201_b.03","mag201_b.04","mag201_b.05",
                "mag201_b.06","mag201_b.07","mag201_b.08","mag201_b.09","mag201_b.10","mag201_b.11","mag201_b.12","mag201_b.13","mag201_b.14","mag201_b.15","mag201_b.16","mag201_b.17","mag201_b.18","mag201_b.19","mag201_b.20","mag201_b.21","mag201_b.22","mag201_b.23","mag201_b.24","mag201_b.25",
                "mag201_b.26","mag201_b.27","mag201_b.28","mag201_b.29","mag201_b.30","mag201_b.31","mag201_b.32","mag201_b.33","mag201_b.34","mag201_b.35","mag201_b.36","mag201_b.37","mag201_b.38","mag201_b.39","mag202_b.02","mag202_b.03","mag202_b.04","mag202_b.05","mag202_b.06","mag202_b.07",
                "mag202_b.08","mag202_b.09","mag202_b.10","mag202_b.11","mag202_b.12","mag203_b.02","mag203_b.03","mag203_b.04","mag203_b.05","mag203_b.06","mag203_b.07","mag203_b.08","mag203_b.09","mag203_b.10","mag203_b.11","mag203_b.12","mag203_b.13","mag203_b.14","mag203_b.15","mag204_b.02",
                "mag204_b.03","mag204_b.04","mag204_b.05","mag204_b.06","mag204_b.07","mag204_b.08","mag204_b.09","mag204_b.10","mag204_b.11","mag205_b.02","mag205_b.03","mag205_b.04","mag205_b.05","mag205_b.06","mag205_b.07","mag205_b.08","mag205_b.09","mag205_b.10","mag205_b.11","mag205_b.12",
                "mag205_b.13","mag205_b.14","mag205_b.15","mag205_b.16","mag205_b.17","mag205_b.18","mag205_b.19","mag205_b.20","mag205_b.21","mag205_b.22","mag205_b.23","mag205_b.24","mag205_b.25","mag205_b.26","mag205_b.27","mag205_b.28","mag205_b.29","mag205_b.30","mag205_b.31","mag205_b.32",
                "mag205_b.33","mag205_b.34","mag205_b.35","mag205_b.36","mag205_b.37","mag205_b.38","mag205_b.39","mag205_b.40","mag205_b.41","mag205_b.42","mag205_b.43","mag205_b.44","mag205_b.45","mag205_b.46","mag205_b.47","mag205_b.48","mag205_b.49","mag205_b.50","mag205_b.51","mag205_b.52",
                "mag205_b.53","mag205_b.54","mag205_b.55","mag205_b.56","mag209_h.00","mag217_a.dat","mag217_b.dat","mag217_c.dat","mag217_d.dat","mag217_e.dat","mag218_b.02","mag218_b.03","mag218_b.04","mag222_b.02","mag222_b.03","mag250_h.00","mag260_b.02","mag273_h.00","mag273_h.01","mag277_h.00",
                "mag277_h.01","mag324_h.00","mag324_h.01","mag324_h.02","mag324_h.03","mag324_h.04","mag324_h.05","mag324_h.06","mag324_h.07","mag324_h.08","mag324_h.09","mag324_h.m00","mag324_h.s00","mag324_h.s01","mag324_h.s02","mag324_h.t00","mag325_a.dat","mag325_b.dat","mag325_c.dat","mag325_d.dat",
                "mag325_e.dat","mag325_f.dat","mag325_g.dat","mag325_h.dat","mag326_a.dat","mag326_b.dat","mag326_c.dat","mag326_d.dat","mag326_e.dat","mag326_f.dat","mag326_g.dat","mag326_h.dat","mag326_k.dat","mag327_h.dat","mag327_j.dat","mag328_g.dat","mag328_h.dat","mag328_i.dat","mag328_j.dat","mag329_h.dat",
                "mag329_j.dat","mag337_h.t00","mag337_h.t01","mag337_h.t02","mag337_h.t03","mag337_h.t04","mag337_h.t05","mag337_h.t06","mag339_a.dat","mag339_b.dat","mag339_c.dat","mag999_a.dat"
            };
        }

        public static bool[] DefaultComp()
        {
            return new bool[] 
            {
                true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,false,true,false,
                false,false,true,true,true,false,false,true,true,true,true,true,true,true,true,true,true,true,false,false,
                true,false,true,true,true,false,true,true,false,true,true,false,true,true,true,false,true,false,true,false,
                true,true,false,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,
                true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,
                true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,
                true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,
                true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,
                true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,
                true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,
                true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,
                true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,
                true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,
                true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,
                true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,
                true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,
                true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,
                true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,
                true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,
                true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,
                true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,
                true,true,true,true,true,true,true,true,true,true,false,false,false,true,false,false,false,true,true,true,
                true,true,true,true,true,false,true,true,true,true,true,true,true,false,true,true,true,true,true,false,
                true,false,false,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,
                true,true,true,true,false,true,true,true,true,true,true,true,true,false,false,true,true,true,true,true,
                true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,false,
                true,true,true,true,false,true,true,true,true,true,true,true,true,true,true,false,true,true,true,true,
                true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,
                true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,
                true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,
                true,true,true,true,true,true,true,true,true,true,true,true,false,true,true,true,true,true,true,true,
                true,true,false,true,true,true,false,true,true,true,true,true,true,true,false,false,true,true,true,true,
                true,false,true,false,false,false,true,true,true,false,false,false,false,true,true,true,true,true,true,true,
                false,true,true,true,true,true,true,true,true,true,true,true,true,true,true,false,true,true,true,true,
                true,true,true,true,true,false,true,true,true,true,true,true,true,true,false,true,true,true,true,true,
                true,true,false,true,true,true,true,false,true,true,false,true,true,false,true,true,true,false,true,false,
                true,true,true,true,false,true,true,false,true,true,true,true,true,true,true,true,true,true,true,true,
                true,true,true,true,true,true,true,false,true,true,true,true,true,true,true,true,true,true,true,true,
                true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,false,true,
                true,true,true,false,true,true,true,true,true,false,true,true,true,true,false,true,true,true,true,true,
                true,false,true,true,true,false,false,false,true,true,false,true,true,true,true,true,true,true,false,true,
                false,true,false,true,true,true,true,true,true,false,true,false,false,true,true,true,true,true,true,true,
                true,true,true,true,true,true,true,true,true,true,true,true
            };
        }

        public static Hashtable DefaultNamesCompRelation()
        {
            return new Hashtable()
            {
                {"a0stg012.x",true},{"a8def.tim",true},{"a9btlfnt.bft",true},{"b0wave.dat",true},{"c0m015.dat",true},{"c0m051.dat",true},{"c0m095.dat",true},{"c0m096.dat",true},{"d0c000.dat",true},{"d0w000.dat",true},{"d3c007.dat",true},{"d3w018.dat",true},{"mag005_b.02",true},{"mag005_b.03",true},{"mag005_b.04",true},{"mag005_b.05",true},{"mag005_b.06",true},{"mag005_b.07",true},{"mag005_b.08",false},{"mag005_b.09",true},{"mag005_b.10",false},
                {"mag005_b.11",false},{"mag005_b.12",false},{"mag005_b.13",true},{"mag005_b.14",true},{"mag005_b.15",true},{"mag005_b.16",false},{"mag005_b.17",false},{"mag046_b.1t0",true},{"mag046_b.1t1",true},{"mag046_b.1t2",true},{"mag161_a.dat",true},{"mag163_a.dat",true},{"mag163_b.dat",true},{"mag164_a.dat",true},{"mag164_b.dat",true},{"mag164_c.dat",true},{"mag184_d.dat",true},{"mag184_e.dat",true},{"mag184_f.dat",false},{"mag184_g.dat",false},
                {"mag184_h.dat",true},{"mag184_i.dat",false},{"mag200_b.02",true},{"mag200_b.03",true},{"mag200_b.04",true},{"mag200_b.05",false},{"mag200_b.06",true},{"mag200_b.07",true},{"mag200_b.08",false},{"mag200_b.09",true},{"mag200_b.10",true},{"mag200_b.11",false},{"mag200_b.12",true},{"mag290_h.00",true},{"mag290_h.01",true},{"mag290_h.02",false},{"mag290_h.03",true},{"mag290_h.04",false},{"mag290_h.05",true},{"mag290_h.06",false},
                {"mag290_h.07",true},{"mag290_h.t00",true},{"r0win.dat",false},{"scene.out",true},{"ma8def_0.tim",true},{"ma8def_1.tim",true},{"ma8def_2.tim",true},{"ma8def_p.0",true},{"ma8def_p.1",true},{"ma8def_p.2",true},{"ma8def_p.3",true},{"a0stg000.x",true},{"a0stg001.x",true},{"a0stg002.x",true},{"a0stg003.x",true},{"a0stg004.x",true},{"a0stg005.x",true},{"a0stg006.x",true},{"a0stg007.x",true},{"a0stg008.x",true},
                {"a0stg009.x",true},{"a0stg010.x",true},{"a0stg011.x",true},{"a0stg013.x",true},{"a0stg014.x",true},{"a0stg015.x",true},{"a0stg016.x",true},{"a0stg017.x",true},{"a0stg018.x",true},{"a0stg019.x",true},{"a0stg020.x",true},{"a0stg021.x",true},{"a0stg022.x",true},{"a0stg023.x",true},{"a0stg024.x",true},{"a0stg025.x",true},{"a0stg026.x",true},{"a0stg027.x",true},{"a0stg028.x",true},{"a0stg029.x",true},
                {"a0stg030.x",true},{"a0stg031.x",true},{"a0stg032.x",true},{"a0stg033.x",true},{"a0stg034.x",true},{"a0stg035.x",true},{"a0stg036.x",true},{"a0stg037.x",true},{"a0stg038.x",true},{"a0stg039.x",true},{"a0stg040.x",true},{"a0stg041.x",true},{"a0stg042.x",true},{"a0stg043.x",true},{"a0stg044.x",true},{"a0stg045.x",true},{"a0stg046.x",true},{"a0stg047.x",true},{"a0stg048.x",true},{"a0stg049.x",true},
                {"a0stg050.x",true},{"a0stg051.x",true},{"a0stg052.x",true},{"a0stg053.x",true},{"a0stg054.x",true},{"a0stg055.x",true},{"a0stg056.x",true},{"a0stg057.x",true},{"a0stg058.x",true},{"a0stg059.x",true},{"a0stg060.x",true},{"a0stg061.x",true},{"a0stg062.x",true},{"a0stg063.x",true},{"a0stg064.x",true},{"a0stg065.x",true},{"a0stg066.x",true},{"a0stg067.x",true},{"a0stg068.x",true},{"a0stg069.x",true},
                {"a0stg070.x",true},{"a0stg071.x",true},{"a0stg072.x",true},{"a0stg073.x",true},{"a0stg074.x",true},{"a0stg075.x",true},{"a0stg076.x",true},{"a0stg077.x",true},{"a0stg078.x",true},{"a0stg079.x",true},{"a0stg080.x",true},{"a0stg081.x",true},{"a0stg082.x",true},{"a0stg083.x",true},{"a0stg084.x",true},{"a0stg085.x",true},{"a0stg086.x",true},{"a0stg087.x",true},{"a0stg088.x",true},{"a0stg089.x",true},
                {"a0stg090.x",true},{"a0stg091.x",true},{"a0stg092.x",true},{"a0stg093.x",true},{"a0stg094.x",true},{"a0stg095.x",true},{"a0stg096.x",true},{"a0stg097.x",true},{"a0stg098.x",true},{"a0stg099.x",true},{"a0stg100.x",true},{"a0stg101.x",true},{"a0stg102.x",true},{"a0stg103.x",true},{"a0stg104.x",true},{"a0stg105.x",true},{"a0stg106.x",true},{"a0stg107.x",true},{"a0stg108.x",true},{"a0stg109.x",true},
                {"a0stg110.x",true},{"a0stg111.x",true},{"a0stg112.x",true},{"a0stg113.x",true},{"a0stg114.x",true},{"a0stg115.x",true},{"a0stg116.x",true},{"a0stg117.x",true},{"a0stg118.x",true},{"a0stg119.x",true},{"a0stg120.x",true},{"a0stg121.x",true},{"a0stg122.x",true},{"a0stg123.x",true},{"a0stg124.x",true},{"a0stg125.x",true},{"a0stg126.x",true},{"a0stg127.x",true},{"a0stg128.x",true},{"a0stg129.x",true},
                {"a0stg130.x",true},{"a0stg131.x",true},{"a0stg132.x",true},{"a0stg133.x",true},{"a0stg134.x",true},{"a0stg135.x",true},{"a0stg136.x",true},{"a0stg137.x",true},{"a0stg138.x",true},{"a0stg139.x",true},{"a0stg140.x",true},{"a0stg141.x",true},{"a0stg142.x",true},{"a0stg143.x",true},{"a0stg144.x",true},{"a0stg145.x",true},{"a0stg146.x",true},{"a0stg147.x",true},{"a0stg148.x",true},{"a0stg149.x",true},
                {"a0stg150.x",true},{"a0stg151.x",true},{"a0stg152.x",true},{"a0stg153.x",true},{"a0stg154.x",true},{"a0stg155.x",true},{"a0stg156.x",true},{"a0stg157.x",true},{"a0stg158.x",true},{"a0stg159.x",true},{"a0stg160.x",true},{"a0stg161.x",true},{"a0stg162.x",true},{"c0m000.dat",true},{"c0m001.dat",true},{"c0m002.dat",true},{"c0m003.dat",true},{"c0m004.dat",true},{"c0m005.dat",true},{"c0m006.dat",true},
                {"c0m007.dat",true},{"c0m008.dat",true},{"c0m009.dat",true},{"c0m010.dat",true},{"c0m011.dat",true},{"c0m012.dat",true},{"c0m013.dat",true},{"c0m014.dat",true},{"c0m016.dat",true},{"c0m017.dat",true},{"c0m018.dat",true},{"c0m019.dat",true},{"c0m020.dat",true},{"c0m021.dat",true},{"c0m022.dat",true},{"c0m023.dat",true},{"c0m024.dat",true},{"c0m025.dat",true},{"c0m026.dat",true},{"c0m027.dat",true},
                {"c0m028.dat",true},{"c0m029.dat",true},{"c0m030.dat",true},{"c0m031.dat",true},{"c0m032.dat",true},{"c0m033.dat",true},{"c0m034.dat",true},{"c0m035.dat",true},{"c0m036.dat",true},{"c0m037.dat",true},{"c0m038.dat",true},{"c0m039.dat",true},{"c0m040.dat",true},{"c0m041.dat",true},{"c0m042.dat",true},{"c0m043.dat",true},{"c0m044.dat",true},{"c0m045.dat",true},{"c0m046.dat",true},{"c0m047.dat",true},
                {"c0m048.dat",true},{"c0m049.dat",true},{"c0m050.dat",true},{"c0m052.dat",true},{"c0m053.dat",true},{"c0m054.dat",true},{"c0m055.dat",true},{"c0m056.dat",true},{"c0m057.dat",true},{"c0m058.dat",true},{"c0m059.dat",true},{"c0m060.dat",true},{"c0m061.dat",true},{"c0m062.dat",true},{"c0m063.dat",true},{"c0m064.dat",true},{"c0m065.dat",true},{"c0m066.dat",true},{"c0m067.dat",true},{"c0m068.dat",true},
                {"c0m069.dat",true},{"c0m070.dat",true},{"c0m071.dat",true},{"c0m072.dat",true},{"c0m073.dat",true},{"c0m074.dat",true},{"c0m075.dat",true},{"c0m076.dat",true},{"c0m077.dat",true},{"c0m078.dat",true},{"c0m079.dat",true},{"c0m080.dat",true},{"c0m081.dat",true},{"c0m082.dat",true},{"c0m083.dat",true},{"c0m084.dat",true},{"c0m085.dat",true},{"c0m086.dat",true},{"c0m087.dat",true},{"c0m088.dat",true},
                {"c0m089.dat",true},{"c0m090.dat",true},{"c0m091.dat",true},{"c0m092.dat",true},{"c0m093.dat",true},{"c0m094.dat",true},{"c0m097.dat",true},{"c0m098.dat",true},{"c0m099.dat",true},{"c0m100.dat",true},{"c0m101.dat",true},{"c0m102.dat",true},{"c0m103.dat",true},{"c0m104.dat",true},{"c0m105.dat",true},{"c0m106.dat",true},{"c0m107.dat",true},{"c0m108.dat",true},{"c0m109.dat",true},{"c0m110.dat",true},
                {"c0m111.dat",true},{"c0m112.dat",true},{"c0m113.dat",true},{"c0m114.dat",true},{"c0m115.dat",true},{"c0m116.dat",true},{"c0m117.dat",true},{"c0m118.dat",true},{"c0m119.dat",true},{"c0m120.dat",true},{"c0m121.dat",true},{"c0m122.dat",true},{"c0m123.dat",true},{"c0m124.dat",true},{"c0m125.dat",true},{"c0m126.dat",true},{"c0m127.dat",true},{"c0m128.dat",true},{"c0m129.dat",true},{"c0m130.dat",true},
                {"c0m131.dat",true},{"c0m132.dat",true},{"c0m133.dat",true},{"c0m134.dat",true},{"c0m135.dat",true},{"c0m136.dat",true},{"c0m137.dat",true},{"c0m138.dat",true},{"c0m139.dat",true},{"c0m140.dat",true},{"c0m141.dat",true},{"c0m142.dat",true},{"c0m143.dat",true},{"c0m144.dat",true},{"c0m145.dat",true},{"c0m146.dat",true},{"c0m147.dat",true},{"c0m148.dat",true},{"c0m149.dat",true},{"c0m150.dat",true},
                {"c0m151.dat",true},{"c0m152.dat",true},{"c0m153.dat",true},{"c0m154.dat",true},{"c0m155.dat",true},{"c0m156.dat",true},{"c0m157.dat",true},{"c0m158.dat",true},{"c0m159.dat",true},{"c0m160.dat",true},{"c0m161.dat",true},{"c0m162.dat",true},{"c0m163.dat",true},{"c0m164.dat",true},{"c0m165.dat",true},{"c0m166.dat",true},{"c0m167.dat",true},{"c0m168.dat",true},{"c0m169.dat",true},{"c0m170.dat",true},
                {"c0m171.dat",true},{"c0m172.dat",true},{"c0m173.dat",true},{"c0m174.dat",true},{"c0m175.dat",true},{"c0m176.dat",true},{"c0m177.dat",true},{"c0m178.dat",true},{"c0m179.dat",true},{"c0m180.dat",true},{"c0m181.dat",true},{"c0m182.dat",true},{"c0m183.dat",true},{"c0m184.dat",true},{"c0m185.dat",true},{"c0m186.dat",true},{"c0m187.dat",true},{"c0m188.dat",true},{"c0m189.dat",true},{"c0m190.dat",true},
                {"c0m191.dat",true},{"c0m192.dat",true},{"c0m193.dat",true},{"c0m194.dat",true},{"c0m195.dat",true},{"c0m196.dat",true},{"c0m197.dat",true},{"c0m198.dat",true},{"c0m199.dat",true},{"d0c001.dat",true},{"d0w001.dat",false},{"d0w002.dat",false},{"d0w003.dat",false},{"d0w004.dat",true},{"d0w005.dat",false},{"d0w006.dat",false},{"d0w007.dat",false},{"d1c003.dat",true},{"d1c004.dat",true},{"d1w008.dat",true},
                {"d1w009.dat",true},{"d1w010.dat",true},{"d1w011.dat",true},{"d2c006.dat",true},{"d2w013.dat",true},{"d2w014.dat",false},{"d2w015.dat",true},{"d2w016.dat",true},{"d3w019.dat",true},{"d3w020.dat",true},{"d3w021.dat",true},{"d4c009.dat",true},{"d4w023.dat",true},{"d4w024.dat",false},{"d4w025.dat",true},{"d4w026.dat",true},{"d4w027.dat",true},{"d5c011.dat",true},{"d5c012.dat",true},{"d5w028.dat",false},
                {"d5w029.dat",true},{"d5w030.dat",false},{"d5w031.dat",false},{"d6c014.dat",true},{"d6w033.dat",true},{"d7c016.dat",true},{"d8c017.dat",true},{"d8c018.dat",true},{"d8w035.dat",true},{"d9c019.dat",true},{"d9c020.dat",true},{"d9w037.dat",true},{"dac021.dat",true},{"dac022.dat",true},{"daw039.dat",true},{"mag007_b.1s0",true},{"mag007_b.1s1",true},{"mag007_b.1s2",true},{"mag007_b.1t0",true},{"mag007_b.1t1",true},
                {"mag064_h.00",true},{"mag064_h.01",true},{"mag064_h.02",true},{"mag064_h.03",true},{"mag076_b.02",false},{"mag076_b.03",true},{"mag076_b.04",true},{"mag076_b.05",true},{"mag078_b.1s0",true},{"mag078_b.1s1",true},{"mag078_b.1s2",true},{"mag078_b.1s3",true},{"mag078_b.1t0",true},{"mag078_b.9m0",false},{"mag084_b.1t0",false},{"mag084_b.1t1",true},{"mag084_b.1t2",true},{"mag085_b.1t0",true},{"mag085_b.1t1",true},{"mag086_b.1s0",true},
                {"mag086_b.1t0",true},{"mag086_b.1t1",true},{"mag087_b.1p0",true},{"mag087_b.1r0",true},{"mag087_b.1r1",true},{"mag087_b.1s0",true},{"mag087_b.1t0",true},{"mag087_b.1t1",true},{"mag088_b.1s0",true},{"mag088_b.1s1",true},{"mag088_b.1t0",true},{"mag088_b.1t1",true},{"mag088_b.2p0",true},{"mag088_b.2p1",true},{"mag088_b.2s0",true},{"mag088_b.2s1",true},{"mag088_b.2t0",true},{"mag088_b.2t1",true},{"mag089_b.1t0",true},{"mag089_b.1z0",false},
                {"mag094_b.1s0",true},{"mag094_b.1t0",true},{"mag094_b.1t1",true},{"mag094_b.1t2",true},{"mag094_b.1t3",false},{"mag094_b.1t4",true},{"mag094_b.1t5",true},{"mag094_b.2e0",true},{"mag094_b.2p0",true},{"mag094_b.2r0",true},{"mag094_b.2r1",true},{"mag094_b.2s0",true},{"mag094_b.2s1",true},{"mag094_b.2s2",true},{"mag094_b.2s3",true},{"mag094_b.2z0",false},{"mag094_b.3p0",true},{"mag094_b.3s0",true},{"mag094_b.3t0",true},{"mag094_b.3t1",true},
                {"mag095_b.1t0",true},{"mag095_b.1t1",true},{"mag095_b.1t2",true},{"mag095_b.1t3",true},{"mag096_b.1t0",true},{"mag096_b.1t1",true},{"mag096_b.1t2",true},{"mag096_b.2s0",true},{"mag096_b.2t0",true},{"mag096_b.2t1",true},{"mag096_b.3p0",true},{"mag096_b.3s0",true},{"mag096_b.3s1",true},{"mag096_b.3t0",true},{"mag096_b.3t1",true},{"mag096_b.3t2",true},{"mag097_b.1t0",true},{"mag097_b.1t1",true},{"mag097_b.1t2",true},{"mag097_b.2s0",true},
                {"mag097_b.2t0",true},{"mag097_b.2t1",true},{"mag097_b.3p0",true},{"mag097_b.3s0",true},{"mag097_b.3s1",true},{"mag097_b.3s2",true},{"mag097_b.3t0",true},{"mag097_b.3t1",true},{"mag097_b.3t2",true},{"mag097_b.3t3",true},{"mag098_b.1t0",true},{"mag098_b.1t1",true},{"mag098_b.1t2",true},{"mag098_b.2s0",true},{"mag098_b.2t0",true},{"mag098_b.2t1",true},{"mag098_b.3s0",true},{"mag098_b.3s1",true},{"mag098_b.3s2",true},{"mag098_b.3t0",true},
                {"mag098_b.3t1",true},{"mag098_b.4p0",true},{"mag098_b.4r0",true},{"mag098_b.4r1",true},{"mag098_b.4s0",true},{"mag098_b.4s1",true},{"mag098_b.4s2",true},{"mag098_b.4t0",true},{"mag098_b.4t1",true},{"mag098_b.4t2",true},{"mag098_b.4t3",true},{"mag099_b.1t0",true},{"mag099_b.1t1",true},{"mag099_b.1t2",true},{"mag099_b.2s0",true},{"mag099_b.2t0",true},{"mag099_b.2t1",true},{"mag099_b.3p0",true},{"mag099_b.3s0",true},{"mag099_b.3t0",true},
                {"mag099_b.4e0",true},{"mag099_b.4t0",true},{"mag099_b.4t1",true},{"mag099_b.5p0",true},{"mag099_b.5s0",true},{"mag099_b.5t0",true},{"mag099_b.5t1",true},{"mag115_h.00",true},{"mag115_h.01",true},{"mag115_h.02",true},{"mag115_h.03",true},{"mag115_h.04",true},{"mag115_h.05",false},{"mag115_h.06",true},{"mag115_h.07",true},{"mag115_h.08",true},{"mag115_h.09",true},{"mag115_h.10",true},{"mag115_h.11",true},{"mag115_h.12",true},
                {"mag115_h.13",true},{"mag115_h.14",true},{"mag115_h.15",false},{"mag115_h.16",true},{"mag115_h.17",true},{"mag115_h.18",true},{"mag115_h.19",false},{"mag115_h.20",true},{"mag115_h.21",true},{"mag115_h.22",true},{"mag139_h.00",true},{"mag139_h.01",true},{"mag139_h.02",true},{"mag139_h.03",true},{"mag139_h.04",false},{"mag139_h.05",false},{"mag139_h.06",true},{"mag139_h.07",true},{"mag139_h.08",true},{"mag186_a.dat",true},
                {"mag186_b.dat",true},{"mag186_c.dat",false},{"mag186_d.dat",true},{"mag186_e.dat",false},{"mag186_f.dat",false},{"mag186_g.dat",false},{"mag190_a.dat",true},{"mag190_b.dat",true},{"mag190_c.dat",true},{"mag190_d.dat",false},{"mag190_e.dat",false},{"mag190_f.dat",false},{"mag190_g.dat",false},{"mag199_a.dat",true},{"mag199_b.dat",true},{"mag199_c.dat",true},{"mag201_b.02",true},{"mag201_b.03",true},{"mag201_b.04",true},{"mag201_b.05",true},
                {"mag201_b.06",false},{"mag201_b.07",true},{"mag201_b.08",true},{"mag201_b.09",true},{"mag201_b.10",true},{"mag201_b.11",true},{"mag201_b.12",true},{"mag201_b.13",true},{"mag201_b.14",true},{"mag201_b.15",true},{"mag201_b.16",true},{"mag201_b.17",true},{"mag201_b.18",true},{"mag201_b.19",true},{"mag201_b.20",true},{"mag201_b.21",false},{"mag201_b.22",true},{"mag201_b.23",true},{"mag201_b.24",true},{"mag201_b.25",true},
                {"mag201_b.26",true},{"mag201_b.27",true},{"mag201_b.28",true},{"mag201_b.29",true},{"mag201_b.30",true},{"mag201_b.31",false},{"mag201_b.32",true},{"mag201_b.33",true},{"mag201_b.34",true},{"mag201_b.35",true},{"mag201_b.36",true},{"mag201_b.37",true},{"mag201_b.38",true},{"mag201_b.39",true},{"mag202_b.02",false},{"mag202_b.03",true},{"mag202_b.04",true},{"mag202_b.05",true},{"mag202_b.06",true},{"mag202_b.07",true},
                {"mag202_b.08",true},{"mag202_b.09",true},{"mag202_b.10",false},{"mag202_b.11",true},{"mag202_b.12",true},{"mag203_b.02",true},{"mag203_b.03",true},{"mag203_b.04",false},{"mag203_b.05",true},{"mag203_b.06",true},{"mag203_b.07",false},{"mag203_b.08",true},{"mag203_b.09",true},{"mag203_b.10",false},{"mag203_b.11",true},{"mag203_b.12",true},{"mag203_b.13",true},{"mag203_b.14",false},{"mag203_b.15",true},{"mag204_b.02",false},
                {"mag204_b.03",true},{"mag204_b.04",true},{"mag204_b.05",true},{"mag204_b.06",true},{"mag204_b.07",false},{"mag204_b.08",true},{"mag204_b.09",true},{"mag204_b.10",false},{"mag204_b.11",true},{"mag205_b.02",true},{"mag205_b.03",true},{"mag205_b.04",true},{"mag205_b.05",true},{"mag205_b.06",true},{"mag205_b.07",true},{"mag205_b.08",true},{"mag205_b.09",true},{"mag205_b.10",true},{"mag205_b.11",true},{"mag205_b.12",true},
                {"mag205_b.13",true},{"mag205_b.14",true},{"mag205_b.15",true},{"mag205_b.16",true},{"mag205_b.17",true},{"mag205_b.18",true},{"mag205_b.19",true},{"mag205_b.20",false},{"mag205_b.21",true},{"mag205_b.22",true},{"mag205_b.23",true},{"mag205_b.24",true},{"mag205_b.25",true},{"mag205_b.26",true},{"mag205_b.27",true},{"mag205_b.28",true},{"mag205_b.29",true},{"mag205_b.30",true},{"mag205_b.31",true},{"mag205_b.32",true},
                {"mag205_b.33",true},{"mag205_b.34",true},{"mag205_b.35",true},{"mag205_b.36",true},{"mag205_b.37",true},{"mag205_b.38",true},{"mag205_b.39",true},{"mag205_b.40",true},{"mag205_b.41",true},{"mag205_b.42",true},{"mag205_b.43",true},{"mag205_b.44",true},{"mag205_b.45",true},{"mag205_b.46",true},{"mag205_b.47",true},{"mag205_b.48",true},{"mag205_b.49",true},{"mag205_b.50",true},{"mag205_b.51",false},{"mag205_b.52",true},
                {"mag205_b.53",true},{"mag205_b.54",true},{"mag205_b.55",true},{"mag205_b.56",false},{"mag209_h.00",true},{"mag217_a.dat",true},{"mag217_b.dat",true},{"mag217_c.dat",true},{"mag217_d.dat",true},{"mag217_e.dat",false},{"mag218_b.02",true},{"mag218_b.03",true},{"mag218_b.04",true},{"mag222_b.02",true},{"mag222_b.03",false},{"mag250_h.00",true},{"mag260_b.02",true},{"mag273_h.00",true},{"mag273_h.01",true},{"mag277_h.00",true},
                {"mag277_h.01",true},{"mag324_h.00",false},{"mag324_h.01",true},{"mag324_h.02",true},{"mag324_h.03",true},{"mag324_h.04",false},{"mag324_h.05",false},{"mag324_h.06",false},{"mag324_h.07",true},{"mag324_h.08",true},{"mag324_h.09",false},{"mag324_h.m00",true},{"mag324_h.s00",true},{"mag324_h.s01",true},{"mag324_h.s02",true},{"mag324_h.t00",true},{"mag325_a.dat",true},{"mag325_b.dat",true},{"mag325_c.dat",false},{"mag325_d.dat",true},
                {"mag325_e.dat",false},{"mag325_f.dat",true},{"mag325_g.dat",false},{"mag325_h.dat",true},{"mag326_a.dat",true},{"mag326_b.dat",true},{"mag326_c.dat",true},{"mag326_d.dat",true},{"mag326_e.dat",true},{"mag326_f.dat",false},{"mag326_g.dat",true},{"mag326_h.dat",false},{"mag326_k.dat",false},{"mag327_h.dat",true},{"mag327_j.dat",true},{"mag328_g.dat",true},{"mag328_h.dat",true},{"mag328_i.dat",true},{"mag328_j.dat",true},{"mag329_h.dat",true},
                {"mag329_j.dat",true},{"mag337_h.t00",true},{"mag337_h.t01",true},{"mag337_h.t02",true},{"mag337_h.t03",true},{"mag337_h.t04",true},{"mag337_h.t05",true},{"mag337_h.t06",true},{"mag339_a.dat",true},{"mag339_b.dat",true},{"mag339_c.dat",true},{"mag999_a.dat",true}
            };
        }

        #endregion

        #region GetBattleFiles

        //virker
        private BattleFile GetBattleFile(string name)
        {
            return GetBattleFile(name, BattlePath, false, simpleNames);
        }

        //virker
        private BattleFile GetBattleFile(int index)
        {
            return GetBattleFile(index, BattlePath, false, simpleNames[index], true);
        }

        public static BattleFile GetBattleFile(string name, string dir)
        {
            return GetBattleFile(name, dir, true, null);
        }

        //virker
        private static BattleFile GetBattleFile(string name, string dir, bool check, string[] names)
        {
            if (check)
            {
                if (string.IsNullOrEmpty(dir))
                    throw new ArgumentException("Path cannot be empty.", "dir");
                AddDirSeperator(ref dir);
            }
            name = name.ToLower();
            
            if (check || names == null) 
                names = GetFileNames(dir + BATTLE_FL, true);

            if (names != null)
            {
                for (int i = 0; i < names.Length; i++)
                {
                    if (name == names[i].ToLower())
                        return GetBattleFile(i, dir);
                }
            }
            else
            {
                throw new Exception("battle.fs may not have been found in choosen dir, or class not properly initiated.");
            }
            
            throw new ArgumentException("File Name does not exsist.", "name");
        }

        public static BattleFile GetBattleFile(int index, string dir)
        {
            return GetBattleFile(index, dir, true, null, true);
        }

        //virker
        private static BattleFile GetBattleFile(int index, string dir, bool check, string name, bool decompress)
        {
            if (check)
            {
                if (string.IsNullOrEmpty(dir))
                    throw new ArgumentException("Path cannot be empty", "dir");
                AddDirSeperator(ref dir);

                if (!File.Exists(dir + BATTLE_FS) ||
                    !File.Exists(dir + BATTLE_FI) ||
                    !File.Exists(dir + BATTLE_FL))
                    throw new Exception("You need all related battle files in chosen dir.");
            }

            //if (index > 435)
            //    index.ToString();

            byte[] fiFile = new byte[BFI_INC];
            FileStream fi = new FileStream(dir + BATTLE_FI, FileMode.Open, FileAccess.Read);
            FileStream fs = new FileStream(dir + BATTLE_FS, FileMode.Open, FileAccess.Read);
            //int count = index; 
            BattleFileInfo info = new BattleFileInfo(); uint end = 0, x = 0;


            int pos = BFI_INC * index;//(BFI_INC * count);
            if(pos > fi.Length - BFI_INC)
                throw new Exception("Couldn't extract wanted data from battle.fi: unexpected file position.");
            fi.Position = pos;
            fi.Read(fiFile, 0, BFI_INC);

            info.unpackedFileLength = BitConverter.ToUInt32(fiFile, UNPACKED_LENGTH_OFFSET);
            info.fileStartOffset = BitConverter.ToUInt32(fiFile, LOCATION_OFFSET);
            info.compressed = BitConverter.ToBoolean(fiFile, LZS_OFFSET);
            do
            {
                if (fi.Position > fi.Length - BFI_INC)
                {
                    end = (uint)fs.Length; break;
                }
                else
                {
                    //fi.Position += BFI_INC;
                    fi.Read(fiFile, 0, BFI_INC);
                    end = BitConverter.ToUInt32(fiFile, LOCATION_OFFSET);
                    x = BitConverter.ToUInt32(fiFile, UNPACKED_LENGTH_OFFSET);
                }
            }
            while (end == 0 || x == 0);

            fi.Close(); fi.Dispose();
            //GC.Collect(); GC.WaitForPendingFinalizers();

            BattleFile file = new BattleFile();
            if (string.IsNullOrEmpty(name))
            {
                try
                {
                    file.Name = GetFileNames(dir + BATTLE_FL, true)[index];
                }
                catch (Exception ex)
                {
                    throw new Exception("Index may be out of bound for battle.fl." + Environment.NewLine + ex.Message);
                }
            }
            else file.Name = name;

            //update index in case of iteration.
            //index = count;

            SetBFData(ref info, ref file, end, fs, decompress);
            fs.Close(); fs.Dispose();
            GC.Collect(); GC.WaitForPendingFinalizers();

            return file;
        }

        public static BattleFile GetDefaultBattleFile(string pathAndFile)
        {
            Hashtable ht = DefaultNamesCompRelation();
            return GetDefaultBattleFile(pathAndFile, ht);
        }

        /// <summary>
        /// Gets a BattleFile based on a file. It's assumed the file is NOT compressed. File location in battle.fs will be unknown.
        /// </summary>
        /// <param name="pathAndFile">The absolute path to the file to associate the BattleFile with.</param>
        /// <returns>The BattleFile in an assumed decompressed state. File location in battle.fs will be unknown..</returns>
        public static BattleFile GetDefaultBattleFile(string pathAndFile, Hashtable ht)
        {
            
            pathAndFile = pathAndFile.ToLower();

            if(!File.Exists(pathAndFile))
                throw new ArgumentException("File does not exist.", "pathAndFile");
            string name = pathAndFile;
            TrimFolders(ref name);
            if (!ht.ContainsKey(name))
                throw new ArgumentException("Not a valid battle file name.", "pathAndFile");

            BattleFileInfo info = new BattleFileInfo();
            info.compressed = (bool)ht[name];

            BattleFile file = new BattleFile();

            file.Data = File.ReadAllBytes(pathAndFile);
            info.unpackedFileLength = (uint)file.Data.Length;
            if (info.unpackedFileLength == 0) info.compressed = false;

            file.Info = info;
            file.Name = name;
            return file;
        }

        #endregion

        #region Misc.

        public static void EncodeBattleFile(ref BattleFile file)
        {
            using (MemoryStream stream = new MemoryStream(file.Data, 0, file.Data.Length, true))
            {
                file.Info.ChangeUnpackedLength(file.Data);
                file.Data = LZSS.Encode(stream); stream.Close();
            }
        }

        private static void SetBFData(ref BattleFileInfo info, ref BattleFile file, uint end, FileStream stream, bool decompress)
        {
            if (info.unpackedFileLength > 0)
            {
                if (info.compressed && decompress)
                {
                    //start offset + 4 because the file has a 4 byte header (file length as 4 bytes).
                    file.Data = LZSS.Decode(stream, (long)info.fileStartOffset + 4, end);
                    //Should be the same, but just in case.
                    info.ChangeUnpackedLength(file.Data);// .unpackedFileLength = (uint);
                }
                else
                {
                    uint e = 0; if (info.compressed) e = 4;
                    file.Data = new byte[end - info.fileStartOffset - e];
                    stream.Position = info.fileStartOffset + e;
                    stream.Read(file.Data, 0, (int)file.Data.Length);
                }
            }
            else
            {
                file.Data = new byte[] { };
                info.SetFStart(0);
                info.compressed = false;
            }

            file.Info = info;
        }

        /// <summary>
        /// This method works, but does not belong here.
        /// </summary>
        /// <param name="s">Path to trim folders off.</param>
        public static void TrimFolders(ref string s)
        {
            int i = 0;
            while (s.Contains("" + Path.DirectorySeparatorChar))
            {

                i = s.IndexOf("" + Path.DirectorySeparatorChar) + 1;
                s = s.Remove(0, i);
            }
            while (s.Contains("" + Path.AltDirectorySeparatorChar))
            {

                i = s.IndexOf("" + Path.AltDirectorySeparatorChar) + 1;
                s = s.Remove(0, i);
            }
        }

        /// <summary>
        /// Works but does not belong in this class. Adds directory seperator if not ending with.
        /// </summary>
        /// <param name="str">String to add directory seperator to.</param>
        public static void AddDirSeperator(ref string str)
        {
            if (string.IsNullOrEmpty(str))
            {
                str = "" + Path.DirectorySeparatorChar;
                return;
            }
            if (str[str.Length - 1] != Path.DirectorySeparatorChar &&
                    str[str.Length - 1] != Path.DirectorySeparatorChar)
                str += Path.DirectorySeparatorChar;
        }

        #endregion

    }
}
