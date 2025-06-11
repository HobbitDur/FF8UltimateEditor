using System;
using System.ComponentModel;
using System.Diagnostics;
using System.Drawing;
using System.Globalization;
using System.IO;
using System.Windows.Forms;
using Microsoft.Win32;
using Ifrit.Code;

namespace Ifrit
{
    enum KernelID : byte
    {
        None = 0,
        Magic = 2,
        Item = 4,
        Custom = 8,
    }

    struct Ability
    {
        public KernelID kernelID;
        public byte unknown;
        public ushort abilityID;
        public int startOffset;
    }


    public partial class Main : Form
    {
        #region Constants

        public const string REG_PATH = "Software\\Ifrit";
        private const string formName = "  -  IFRIT  -  Simple FFVIII Enemy Editor v0.11",
                             BadFile = "This is clearly not a ffviii file.\nYou should re-open a valid file before you continue.",
                             FF8_REG32 = "SOFTWARE\\Square Soft, Inc\\FINAL FANTASY VIII\\1.00",
                             FF8_REG64 = "SOFTWARE\\Wow6432Node\\Square Soft, Inc\\FINAL FANTASY VIII\\1.00",
                             APP_PATH = "AppPath";



        private readonly string DATA_FOLDER = Path.DirectorySeparatorChar + "Data";
        /// <summary>
        /// x86 bitness (4).
        /// </summary>
        const byte WIN32 = 4;

        /// <summary>
        /// x64 bitness (8).
        /// </summary>
        const byte WIN64 = 8;


        //pointerOffset is offset in the file as a whole.
        //All others are offsets relevant to the value at pointerOffset + the value of the constant.  
        private const int pointerOffset = 0x1C, c0m127pointerOffset = 4, nameOffset = 0x0, maxNameLength = 24,
                          hp_b1Offset = 0x18, str_b1Offset = 0x1C, vit_b1Offset = 0x20, mag_b1Offset = 0x24, spr_b1Offset = 0x28, spd_b1Offset = 0x2C, eva_b1Offset = 0x30,
                          med_lvlOffset = 0xF4, high_lvlOffset = 0xF5, extra_EXPOffset = 0x100, EXP_Offset = 0x102,
                          low_lvlMagOffset = 0x104, med_lvlMagOffset = 0x10C, high_lvlMagOffset = 0x114,
                          low_lvlMugOffset = 0x11C, med_lvlMugOffset = 0x124, high_lvlMugOffset = 0x12C,
                          low_lvlDropOffset = 0x134, med_lvlDropOffset = 0x13C, high_lvlDropOffset = 0x144,
                          mugRateOffset = 0x14C, dropRateOffset = 0x14D, apOffset = 0x14F,
                          elemDefOffset = 0x160, statusDefOffset = 0x168, devourOffset = 251, cardOffset = 248,
                          abilitiesOffset = 52;

        //The variables under must be considered constants.

        /// <summary>
        /// The list of text in FFVIII format.
        /// </summary>
        private string textFormat
        {
            get
            {
                switch(langBye) {
                    case 1:
                    return Properties.Resources.textformat_greek;
                    default:
                    return Properties.Resources.textformat;
                }
            }
        }
        /// <summary>
        /// Magic in hex values.
        /// </summary>
        private readonly string magic = Properties.Resources.magic;
        /// <summary>
        /// Items in hex values.
        /// </summary>
        private readonly string items = Properties.Resources.items;
        /// <summary>
        /// Devour in hex values.
        /// </summary>
        private readonly string devour = Properties.Resources.devour;
        /// <summary>
        /// Cards in hex values.
        /// </summary>
        private readonly string cards = Properties.Resources.cards;

        #endregion

        #region Variables

        /// <summary>
        /// Language byte identifier.
        /// </summary>
        byte langBye;

        Ability[] abilities = new Ability[48];

        Porter extracter;

        /// <summary>
        /// pointer value. Points to where offset 0x00 of actual data starts
        /// </summary>
        private int pointer = 0;
        /// <summary>
        /// The file name. Does not include path.
        /// </summary>
        public string fileName = "";
        /// <summary>
        /// File to save.
        /// </summary>
        public string fileSave = "";
        /// <summary>
        /// The file path. Does not include name.
        /// </summary>
        private string filePath = "";
        /// <summary>
        /// The folder path. Used when opening a folder.
        /// </summary>
        private string folderPath = "";
        /// <summary>
        /// Used to convert to other values.
        /// </summary>
        private string hexValue = "";
        /// <summary>
        /// Enemy Name.
        /// </summary>
        private string eName = "";
        /// <summary>
        /// The key used towards the windows registry.
        /// </summary>
        RegistryKey regKey;
        /// <summary>
        /// General file stream.
        /// </summary>
        FileStream fileStream;
        /// <summary>
        /// Used when a file is opened.
        /// </summary>
        byte[] bufferB;
        /// <summary>
        /// Copy of the buffer.
        /// To check if save is needed.
        /// </summary>
        byte[] bufferBCopy;
        /// <summary>
        /// Used when filling the listbox.
        /// </summary>
        byte[] bufferB2;
        /// <summary>
        /// A collection of all the files in the listbox.
        /// The indexes are the same as in the listbox.
        /// </summary>
        string[] files;

        /// <summary>
        /// Operative system the application runs on. 
        /// </summary>
        public OperatingSystem os;

        /// <summary>
        /// OS flags. index 0 = windows, 1 = macosx, 2 = unix 
        /// </summary>
        public bool[] oss = new bool[3];

        /// <summary>
        /// Used to determine wheter the user retries an error or not.
        /// If this equals 'retry' then the program will atempt the same task again upon error.
        /// </summary>
        DialogResult res;

        bool startup = true;
        bool fileOpen = false;
        bool enableSave = false;
        bool validate = true;
        bool reOpenToolWin = false;
        bool avoidList = false;
        bool avoidAskSave = false;
        Report rStats;
        About about;
        /// <summary>
        /// Used to valideate.
        /// </summary>
        TextBox activeTxtb;


        RegistryKey fregKey;
        #endregion

        #region Attributes

        public string DataPath
        {
            get
            {
                if (fregKey == null)
                {
                    fregKey = Registry.LocalMachine.OpenSubKey(FF8_REG32);
                    if (fregKey == null)
                        fregKey = Registry.LocalMachine.OpenSubKey(FF8_REG64);
                }
                string s = (string)GRegistry.GetRegValue(fregKey, APP_PATH, null);
                if (string.IsNullOrEmpty(s)) return s;
                return s + DATA_FOLDER + Path.DirectorySeparatorChar;
            }
        }

        #endregion

        #region Startup

        public Main()
        {
            InitializeComponent();

            //Create Unknowns controls
            int tabIndex = 0;
            for (int i = 336; i < 353; i++)
            {
                Label lbl = new Label();
                NumericUpDown nud = new NumericUpDown();
                lbl.ForeColor = lbl40.ForeColor;
                Panel pnl = new Panel();
                pnl.Width = 120; pnl.Height = 38;
                lbl.Text = "0x" + i.ToString("x"); nud.Tag = i;
                lbl.Width = lbl.Text.Length * 10; nud.Width = 48;
                nud.Location = new Point(lbl.Width + 10, 4);
                nud.TabIndex = tabIndex; tabIndex++;
                lbl.Location = new Point(2, 6);
                flowLayoutPanelUnknowns.Controls.Add(pnl);
                pnl.Controls.Add(lbl); pnl.Controls.Add(nud);
                nud.Minimum = 0; nud.Maximum = 255;
                nud.ValueChanged += new EventHandler(NudChanged);
            }

            //Create abilities controls
            tabIndex = 0;
            for (int i = 0; i < 48; i++)
            {
                ComboBox cb = new ComboBox(); cb.Items.Clear();
                cb.Items.AddRange(new object[] { KernelID.None, KernelID.Magic, KernelID.Item, KernelID.Custom });
                cb.Location = new Point(2, 2); cb.Width = 72; cb.FormattingEnabled = true;
                cb.SelectedIndexChanged += new EventHandler(AbilityChange);
                cb.TabIndex = tabIndex; tabIndex++; cb.Tag = 0;

                //Label lbl = new Label(); lbl.Text = "ID:"; lbl.Location = new Point(cb.Width + 4, 4);
                //lbl.Width = lbl.Text.Length * 9; lbl.ForeColor = lbl40.ForeColor; lbl.Tag = 5;

                NumericUpDown nud = new NumericUpDown(); nud.Width = 68;
                nud.Location = new Point(cb.Width + 4, 2);
                nud.ValueChanged += new EventHandler(AbilityChange);
                nud.Maximum = UInt16.MaxValue; nud.Tag = 2;
                nud.TabIndex = tabIndex; tabIndex++;

                NumericUpDown nud2 = new NumericUpDown(); nud2.Width = 52;
                nud2.Location = new Point(cb.Width + nud.Width + 4, 2);
                nud2.ValueChanged += new EventHandler(AbilityChange);
                nud2.Maximum = Byte.MaxValue; nud2.Tag = 1;
                nud2.TabIndex = tabIndex; tabIndex++;

                Panel p = new Panel(); p.Width = gbAbilitiesLow.Width - 2; p.Height = cb.Height;
                p.Controls.AddRange(new Control[] { cb, nud, nud2 });
                //The tag is the ability index. Use parent of controls to check.
                p.Tag = i;

                if (i < 16) flowLayoutPanel1.Controls.Add(p);
                else if (i < 32) flowLayoutPanel2.Controls.Add(p);
                else flowLayoutPanel3.Controls.Add(p);
            }
        }
        private void Main_Load(object sender, EventArgs e)
        {
            res = DialogResult.OK;
            startup = true;
            fileOpen = false;
            avoidList = false;
            avoidAskSave = false;

            os = Environment.OSVersion;
            oss[0] = os.Platform == PlatformID.Win32Windows | os.Platform == PlatformID.Win32NT;
            oss[2] = os.Platform == PlatformID.Unix;
            oss[1] = os.Platform == PlatformID.MacOSX;

            int bitness = IntPtr.Size;
            //BattleFile f1 = battleFileHandler.DeComp();
            //BattleFile f2 = battleFileHandler.NoDeComp();
            //BattleFile f3 = battleFileHandler[1];
            //BattleFile f4 = battleFileHandler["a8def.tim"];
            //f1.ToString();
            //BattleFileHandler.EncodeBattleFile(ref f1);
            //f1.ToString();
            //battleFileHandler.ExtractBattleFiles();
            //battleFileHandler.PackBattleFiles();

            //battleFileHandler.ExtractBattleFiles();

            try
            {
                //Set the registry key...
                try
                {
                    if (!oss[1] && !oss[2] && oss[0])
                    {
                        regKey = Registry.CurrentUser.CreateSubKey(REG_PATH, RegistryKeyPermissionCheck.ReadWriteSubTree);

                        if (bitness == WIN32 && regKey != null)
                            regKey = Registry.CurrentUser.OpenSubKey(REG_PATH, true);
                        else if (bitness == WIN64)
                            regKey = GRegistry.OpenSubKey(Registry.CurrentUser, REG_PATH, true,
                                GRegistry.eRegWow64Options.KEY_WOW64_64KEY | GRegistry.eRegWow64Options.KEY_ALL_ACCESS);
                    }

                }
                catch (Exception ex) { tslbl2.Text = ex.Message; }
                finally
                {
                    if (oss[1] || oss[2])
                    {

                    }

                    else
                    {
                        if (regKey == null && oss[0])
                            regKey = Registry.CurrentUser.CreateSubKey(REG_PATH, RegistryKeyPermissionCheck.ReadWriteSubTree);
                    }
                }
                SetFormSizeFromReg(regKey);
                splitContainer.SplitterDistance = (int)GRegistry.GetRegValue(regKey, "split", splitContainer.SplitterDistance);

                if (splitContainer.SplitterDistance > this.Width - 15)
                    splitContainer.SplitterDistance = this.Width - 16;

                if (GRegistry.GetRegValue(regKey, "pack_dir", null) == null && !string.IsNullOrEmpty(DataPath))
                {
                    GRegistry.SetRegValue(regKey, "pack_dir", DataPath, RegistryValueKind.String);
                }

                if (Directory.Exists((string)GRegistry.GetRegValue(regKey, "initial_dir", "")))
                {
                    openFileDialog.InitialDirectory = (string)GRegistry.GetRegValue(regKey, "initial_dir", "");
                    if (GRegistry.GetRegValue(regKey, "ex_dir", null) == null)
                        GRegistry.SetRegValue(regKey, "ex_dir", openFileDialog.InitialDirectory, RegistryValueKind.String);

                }
                else
                    openFileDialog.InitialDirectory = "." + Path.DirectorySeparatorChar;


                //Character Table
                if (GRegistry.GetRegValue(regKey, "ct", null) == null)
                {
                    GRegistry.SetRegValue(regKey, "ct", 0, RegistryValueKind.DWord);
                }
                langBye = Convert.ToByte(GRegistry.GetRegValue(regKey, "ct", 0));

                foreach (ToolStripMenuItem item in characterTableToolStripMenuItem.DropDownItems)
                {
                    if (Convert.ToByte(item.Tag) == langBye)
                    {
                        item.Checked = true;
                        item.CheckState = CheckState.Checked; break;
                    }
                }
                //Character Table End

                if (Directory.Exists((string)GRegistry.GetRegValue(regKey, "initial_folder", "")))
                {
                    folderBrowserDialog.SelectedPath = (string)GRegistry.GetRegValue(regKey, "initial_folder", "");
                    folderPath = tslblPath.Text = folderBrowserDialog.SelectedPath;
                    Check_Tool_Text();
                    try
                    {
                        Fill_listBox();
                    }
                    catch (Exception ex)
                    {
                        MessageBox.Show(ex.Message + Environment.NewLine + "There was a problem with one or more of the files in the folder (or folder is empty). Try extracting from a new archive 'Valid files only', and/or delete all files in this folder you know are not valid. Restarting the app is recommended after you fixed the problem.");
                    }
                }
                else
                    folderPath = tslblPath.Text = folderBrowserDialog.SelectedPath = "." + Path.DirectorySeparatorChar;

                toolStripTextBox1.Text = (string)GRegistry.GetRegValue(regKey, "dir_text", "");

                FillCombobox(cbMugLow1, items, 255);
                FillCombobox(cbMugLow2, items, 255);
                FillCombobox(cbMugLow3, items, 255);
                FillCombobox(cbMugLow4, items, 255);

                FillCombobox(cbMugMed1, items, 255);
                FillCombobox(cbMugMed2, items, 255);
                FillCombobox(cbMugMed3, items, 255);
                FillCombobox(cbMugMed4, items, 255);

                FillCombobox(cbMugHigh1, items, 255);
                FillCombobox(cbMugHigh2, items, 255);
                FillCombobox(cbMugHigh3, items, 255);
                FillCombobox(cbMugHigh4, items, 255);

                FillCombobox(cbDropLow1, items, 255);
                FillCombobox(cbDropLow2, items, 255);
                FillCombobox(cbDropLow3, items, 255);
                FillCombobox(cbDropLow4, items, 255);

                FillCombobox(cbDropMed1, items, 255);
                FillCombobox(cbDropMed2, items, 255);
                FillCombobox(cbDropMed3, items, 255);
                FillCombobox(cbDropMed4, items, 255);

                FillCombobox(cbDropHigh1, items, 255);
                FillCombobox(cbDropHigh2, items, 255);
                FillCombobox(cbDropHigh3, items, 255);
                FillCombobox(cbDropHigh4, items, 255);

                FillCombobox(cbDevourLow, devour, 255);
                FillCombobox(cbDevourMed, devour, 255);
                FillCombobox(cbDevourHigh, devour, 255);

                FillCombobox(cbCardLow, cards, 255);
                FillCombobox(cbCardMed, cards, 255);
                FillCombobox(cbCardHigh, cards, 255);

                FillCombobox(cbDrawHigh1, magic, 96);
                FillCombobox(cbDrawHigh2, magic, 96);
                FillCombobox(cbDrawHigh3, magic, 96);
                FillCombobox(cbDrawHigh4, magic, 96);

                FillCombobox(cbDrawMed1, magic, 96);
                FillCombobox(cbDrawMed2, magic, 96);
                FillCombobox(cbDrawMed3, magic, 96);
                FillCombobox(cbDrawMed4, magic, 96);

                FillCombobox(cbDrawLow1, magic, 96);
                FillCombobox(cbDrawLow2, magic, 96);
                FillCombobox(cbDrawLow3, magic, 96);
                FillCombobox(cbDrawLow4, magic, 96);
            }
            catch (Exception ex)
            {
                res = MessageBox.Show(this, ex.Message + "\nPress cancel to exit application.", "Error", MessageBoxButtons.RetryCancel, MessageBoxIcon.Error, MessageBoxDefaultButton.Button1);
                startup = false;
            }
            if (res == DialogResult.Retry)
                Main_Load(sender, e);
            else if (res == DialogResult.Cancel)
            {
                Exit();
            }
            startup = false;
        }
        #endregion

        #region Button Clicks

        private void btnStat_Click(object sender, EventArgs e)
        {
            if (!fileOpen)
                return;
            Text_Validating(null, new CancelEventArgs());
            if (rStats != null)
                rStats.Dispose();
            rStats = new Report(eName, this);
            rStats.Show(this);
        }
        private void Save_Click(object sender, EventArgs e)
        {
            res = DialogResult.Cancel;
            string didSave = "No save occurred";
            try
            {
                Text_Validating(sender, new CancelEventArgs());
                if (enableSave && fileSave != "")
                {
                    avoidList = true;
                    if (!File.Exists(fileSave))
                    {
                        MessageBox.Show(this, "Cannot save. Desired file does not exist.", "No file", MessageBoxButtons.OK, MessageBoxIcon.Error);
                        avoidList = false;
                        return;
                    }

                    fileStream = new FileStream(fileSave, FileMode.Open, FileAccess.Write);
                    if (fileStream.Length > Int32.MaxValue)
                    {
                        MessageBox.Show(this, "Cannot save.\n" + BadFile, "Bad file", MessageBoxButtons.OK, MessageBoxIcon.Error);
                        fileStream.Close();
                        avoidList = false;
                        return;
                    }
                    fileStream.Write(bufferB, 0, (int)fileStream.Length);
                    fileStream.Close();

                    fileStream = new FileStream(fileSave, FileMode.Open, FileAccess.Read);
                    fileStream.Read(bufferBCopy, 0, (int)fileStream.Length);
                    fileStream.Close();

                    didSave = "However the file was saved.";

                    if (this.Text.EndsWith("*"))
                        this.Text = this.Text.TrimEnd('*');
                    tmiSave.Enabled = false;
                    tsbSave.Enabled = false;
                    tslbl2.Text = "       -";

                    int i;
                    string s = fileSave;
                    while (s.Contains("" + Path.DirectorySeparatorChar))
                    {
                        i = s.IndexOf("" + Path.DirectorySeparatorChar) + 1;
                        s = s.Remove(0, i);
                    }

                    i = 0;
                    string s2 = ""; ;
                    for (i = 0; i < listBox.Items.Count; i++)
                    {
                        s2 = listBox.Items[i].ToString();
                        if (s2.Contains(s + " - "))
                        {
                            listBox.Items[i] = s2.Replace(eName, label41.Text.Replace("Real name: ", ""));
                            eName = label41.Text.Replace("Real name: ", "");
                            break;
                        }
                    }
                    this.Text = eName + "/" + s + formName;

                }
                avoidList = false;
            }
            catch (Exception ex)
            {
                res = MessageBox.Show(this, ex.Message + "\n" + didSave, "Error", MessageBoxButtons.RetryCancel, MessageBoxIcon.Error, MessageBoxDefaultButton.Button2);
                fileStream.Close();
                avoidList = false;
            }
            if (res == DialogResult.Retry)
                Save_Click(sender, e);
        }
        private void Open_Click(object sender, EventArgs e)
        {
            res = DialogResult.Cancel;
            avoidAskSave = true;

            try
            {
                if (this.Text.EndsWith("*"))
                {
                    res = MessageBox.Show(this, "Save changes?", "Save", MessageBoxButtons.YesNoCancel, MessageBoxIcon.Question, MessageBoxDefaultButton.Button3);
                    if (res == DialogResult.Cancel)
                        return;
                    else if (res == DialogResult.Yes)
                    {
                        Save_Click(null, null);
                    }

                }
                openFileDialog.InitialDirectory = (string)GRegistry.GetRegValue(regKey, "initial_dir", null);
                openFileDialog.ShowDialog();
            }
            catch (Exception ex)
            {
                res = MessageBox.Show(this, ex.Message, "Error", MessageBoxButtons.RetryCancel, MessageBoxIcon.Error, MessageBoxDefaultButton.Button2);
                avoidAskSave = false;
            }
            if (res == DialogResult.Retry)
                Open_Click(sender, e);
            avoidAskSave = false;
        }
        private void OFolder_Click(object sender, EventArgs e)
        {
            res = DialogResult.Cancel;
            folderBrowserDialog.Description = "Select Folder with Battle Files.";
            folderBrowserDialog.SelectedPath = (string)GRegistry.GetRegValue(regKey, "initial_folder", "");
            folderBrowserDialog.ShowNewFolderButton = false;
            try
            {
                if (folderBrowserDialog.ShowDialog(this) != DialogResult.OK) return;
                folderPath = tslblPath.Text = folderBrowserDialog.SelectedPath;
                if (Fill_listBox() == 1)
                {
                    Check_Tool_Text();
                    GRegistry.SetRegValue(regKey, "initial_folder", folderPath, RegistryValueKind.String);
                    toolStripTextBox1.Text = folderPath;
                }
            }
            catch (Exception ex)
            {
                res = MessageBox.Show(this, ex.Message, "Error", MessageBoxButtons.RetryCancel, MessageBoxIcon.Error, MessageBoxDefaultButton.Button2);
            }
            if (res == DialogResult.Retry)
                OFolder_Click(sender, e);
        }
        private void Help_Click(object sender, EventArgs e)
        {
            try
            {
                Process p = new Process();
                p.StartInfo.FileName = ".\\Ifrit.chm";
                p.Start();
            }
            catch (Exception ex)
            {
                MessageBox.Show(this, ex.Message, "Error", MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
        }
        private void Info_Click(object sender, EventArgs e)
        {
            try
            {
                if (about != null)
                    about.Dispose();
                about = new About();
                about.Show(this);
            }
            catch (Exception ex)
            {
                MessageBox.Show(this, ex.Message, "Error", MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
        }
        private void exitToolStripMenuItem_Click(object sender, EventArgs e)
        {
            Exit();
        }
        private void openFileDialog_FileOk(object sender, CancelEventArgs e)
        {
            res = DialogResult.Cancel;
            try
            {
                this.SuspendLayout();
                listBox.Items.Clear();
                fileSave = fileName;
                fileName = filePath = openFileDialog.FileName;
                Do_Open();

            }
            catch (Exception ex)
            {
                res = MessageBox.Show(this, ex.Message + "\nThis may not have been a valid file.", "Error", MessageBoxButtons.RetryCancel, MessageBoxIcon.Error, MessageBoxDefaultButton.Button2);
            }
            finally
            {
                this.ResumeLayout(false);
                this.PerformLayout();
            }
            if (res == DialogResult.Retry)
                openFileDialog_FileOk(sender, e);
        }

        private void characTableClick(object sender, EventArgs e)
        {

            try
            {
                if (sender is System.Windows.Forms.ToolStripMenuItem)
                {
                    foreach (ToolStripMenuItem item in characterTableToolStripMenuItem.DropDownItems)
                    {
                        item.Checked = false;
                        item.CheckState = CheckState.Unchecked;
                    }
                }
                byte old = langBye;
                langBye = Convert.ToByte((sender as ToolStripMenuItem).Tag);
                if (old != langBye)
                {
                    (sender as ToolStripMenuItem).Checked = true;
                    (sender as ToolStripMenuItem).CheckState = CheckState.Checked;
                    GRegistry.SetRegValue(regKey, "ct", langBye, RegistryValueKind.DWord);
                    if (files != null && files.Length > 0)
                        Fill_listBox();
                    if (fileOpen)
                    {
                        bool oldA = avoidAskSave;
                        avoidAskSave = true;
                        Open_File();
                        avoidAskSave = oldA;
                    }
                }
            }
            catch (Exception ex)
            {
                res = MessageBox.Show(this, ex.Message, "Error", MessageBoxButtons.OK, MessageBoxIcon.Error);
            }

        }

        #endregion

        #region Fill list box
        /// <summary>
        /// Fills the listbox with files stored in the 'folderPath' string.
        /// </summary>
        /// <returns>Returns 1 if successful.</returns>
        private short Fill_listBox()
        {
            int numberOffiles = 0;
            files = Directory.GetFiles(folderPath, "*.dat");
            if (files.Length == 0 && !startup)
            {
                MessageBox.Show(this, "No files found.\nSelect the folder that contains .dat files from battle.fs", "Nothing found", MessageBoxButtons.OK, MessageBoxIcon.Information);
                return 0;
            }
            listBox.Items.Clear();
            int i = 0;
            string s = ""; bool notv = false;

            foreach (string file in files)
            {

                s = file;
                while (s.Contains("" + Path.DirectorySeparatorChar))
                {

                    i = s.IndexOf("" + Path.DirectorySeparatorChar) + 1;
                    s = s.Remove(0, i);
                }
                //if (!notv)
                //{
                //    if (s.Contains("b0wave.dat"))
                //    {
                //        notv = !notv;
                //        continue;
                //    }
                //}

                s += " - ";

                fileStream = new FileStream(file, FileMode.Open, FileAccess.Read);
                try
                {
                    if (fileStream.Length < pointerOffset)
                    {
                        numberOffiles++;
                        s += "Bad file, way too short.";
                        listBox.Items.Add(s);
                        fileStream.Close();
                        continue;
                    }

                    bufferB2 = new byte[24];
                    fileStream.Position = s.Contains("c0m127") ? c0m127pointerOffset : pointerOffset;
                    fileStream.Read(bufferB2, 0, 4);
                    hexValue = Swap_Bytes(bufferB2, 3, 4).ToUpper();
                    pointer = Int32.Parse(hexValue, NumberStyles.HexNumber);
                }
                catch (Exception ex )
                {
                    fileStream.Close();
                    throw ex;
                }
                if (fileStream.Length < (pointerOffset + pointer + statusDefOffset + 0x14))
                {
                    numberOffiles++;
                    s += "Bad file, too short.";
                    listBox.Items.Add(s);
                    fileStream.Close();
                    continue;
                }

                

                fileStream.Position = pointer;
                fileStream.Read(bufferB2, 0, bufferB2.Length);
                foreach (byte b in bufferB2)
                {
                    if (b == 0)
                        break;

                    if (b == 14)
                    {
                        s += "<$>";
                        continue;
                    }
                    else if (b < 0x20)
                        continue;

                    s += Make_Enemy_Name(b);
                }
                numberOffiles++;
                listBox.Items.Add(s);
                fileStream.Close();
            }
            if (numberOffiles <= 0)
            {
                MessageBox.Show(this, BadFile, "Error", MessageBoxButtons.OK, MessageBoxIcon.Stop);
                fileStream.Close();
                return 0;
            }
            return 1;

        }

        private void Go_Click(object sender, EventArgs e)
        {
            res = DialogResult.Cancel;
            try
            {
                if (!Directory.Exists(toolStripTextBox1.Text))
                {
                    MessageBox.Show(this, "The directory doesn't exist.", "No directory", MessageBoxButtons.OK, MessageBoxIcon.Error);
                    return;
                }
                folderPath = tslblPath.Text = toolStripTextBox1.Text;
                if (Fill_listBox() == 1)
                {
                    Check_Tool_Text();
                    GRegistry.SetRegValue(regKey, "dir_text", folderPath, RegistryValueKind.String);
                    GRegistry.SetRegValue(regKey, "initial_folder", folderPath, RegistryValueKind.String);
                }
            }
            catch (Exception ex)
            {
                res = MessageBox.Show(this, ex.Message, "Error", MessageBoxButtons.RetryCancel, MessageBoxIcon.Error, MessageBoxDefaultButton.Button2);
            }
            if (res == DialogResult.Retry)
                Go_Click(sender, e);
        }
        #endregion

        #region Open File

        private void Do_Open()
        {
            res = Open_File();
            if (res == DialogResult.Cancel)
            {
                fileName = filePath = fileSave;
                if (bufferB != null && bufferBCopy != null)
                    fileOpen = true;
            }
        }
        private void listBox_DoubleClick(object sender, EventArgs e)
        {
            if (!avoidList)
            {
                res = DialogResult.Yes;
                try
                {
                    this.SuspendLayout();
                    if (listBox.SelectedItem != null && listBox.SelectedIndex >= 0)
                    {
                        fileSave = fileName;
                        fileName = filePath = files[listBox.SelectedIndex];
                        Do_Open();
                    }
                }
                catch (Exception ex)
                {
                    res = MessageBox.Show(this, ex.Message + "\nThis may not have been a valid file.", "Error", MessageBoxButtons.RetryCancel, MessageBoxIcon.Error, MessageBoxDefaultButton.Button2);
                }
                finally
                {
                    this.ResumeLayout(false);
                    this.PerformLayout();
                }
                if (res == DialogResult.Retry)
                    listBox_DoubleClick(sender, e);
            }

        }
        private DialogResult Open_File()
        {
            fileOpen = false;
            res = DialogResult.No;

            if (this.Text.EndsWith("*") && !avoidAskSave)
            {
                res = MessageBox.Show(this, "Save changes?", "Save", MessageBoxButtons.YesNoCancel, MessageBoxIcon.Question, MessageBoxDefaultButton.Button3);
                if (res == DialogResult.Cancel)
                    return res;
                else if (res == DialogResult.Yes)
                    Save_Click(null, new EventArgs());

            }
            fileStream = new FileStream(fileName, FileMode.Open, FileAccess.Read);
            if (fileStream.Length < pointerOffset)
            {
                Bad_File();
                bufferB = null;
                bufferBCopy = null;
                return DialogResult.Cancel;
            }

            bufferB = new byte[fileStream.Length];
            fileStream.Read(bufferB, 0, (int)fileStream.Length);
            hexValue = Swap_Bytes(bufferB, (fileName.Contains("c0m127") ? c0m127pointerOffset : pointerOffset) + 3, 4).ToUpper();
            pointer = Int32.Parse(hexValue, System.Globalization.NumberStyles.HexNumber);
            if (fileStream.Length < (pointerOffset + pointer + statusDefOffset + 0x20))
            {
                Bad_File();
                bufferB = null;
                bufferBCopy = null;
                return DialogResult.Cancel;
            }
            fileStream.Close();
            fileStream = new FileStream(fileName, FileMode.Open, FileAccess.Read);
            bufferBCopy = new byte[fileStream.Length];
            fileStream.Read(bufferBCopy, 0, (int)fileStream.Length);
            fileStream.Close();
            int i;
            string s = fileName;
            while (s.Contains("\\"))
            {
                i = s.IndexOf("\\") + 1;
                s = s.Remove(0, i);
            }
            this.Text = s + formName;
            i = filePath.LastIndexOf(s);
            if (i > -1)
            {
                filePath = filePath.Remove(i);
                toolStripTextBox1.Text = filePath;
            }

            s = "";
            txtbName.Text = "";
            byte b;
            i = pointer;
            for (int j = 0; j < 25; j++)
            {
                b = bufferB[i + j];
                if (b == 0)
                    break;

                if (b == 14)
                {
                    s += "<$>";
                    continue;
                }
                else if (b < 0x20)
                    continue;
                s += Make_Enemy_Name(b);
            }
            txtbName.Text = s;
            eName = s;
            this.Text = s + "/" + this.Text;
            label41.Text = "Real name: " + s;

            #region Load variables
            validate = false;

            i = 0;
            i = pointer + hp_b1Offset;
            FT(bufferB[i], txtbHP1);
            FT(bufferB[i + 1], txtbHP2);
            FT(bufferB[i + 2], txtbHP3);
            FT(bufferB[i + 3], txtbHP4);

            i = pointer + str_b1Offset;
            FT(bufferB[i], txtbStr1);
            FT(bufferB[i + 1], txtbStr2);
            FT(bufferB[i + 2], txtbStr3);
            FT(bufferB[i + 3], txtbStr4);

            i = pointer + mag_b1Offset;
            FT(bufferB[i], txtbMag1);
            FT(bufferB[i + 1], txtbMag2);
            FT(bufferB[i + 2], txtbMag3);
            FT(bufferB[i + 3], txtbMag4);

            i = pointer + vit_b1Offset;
            FT(bufferB[i], txtbVit1);
            FT(bufferB[i + 1], txtbVit2);
            FT(bufferB[i + 2], txtbVit3);
            FT(bufferB[i + 3], txtbVit4);

            i = pointer + spr_b1Offset;
            FT(bufferB[i], txtbSpr1);
            FT(bufferB[i + 1], txtbSpr2);
            FT(bufferB[i + 2], txtbSpr3);
            FT(bufferB[i + 3], txtbSpr4);

            i = pointer + spd_b1Offset;
            FT(bufferB[i], txtbSpd1);
            FT(bufferB[i + 1], txtbSpd2);
            FT(bufferB[i + 2], txtbSpd3);
            FT(bufferB[i + 3], txtbSpd4);

            i = pointer + eva_b1Offset;
            FT(bufferB[i], txtbEva1);
            FT(bufferB[i + 1], txtbEva2);
            FT(bufferB[i + 2], txtbEva3);
            FT(bufferB[i + 3], txtbEva4);

            i = pointer + apOffset;
            FT(bufferB[i], txtbAP);

            i = pointer + EXP_Offset;
            txtbEXP.Text = Int32.Parse(Swap_Bytes(new byte[] { bufferB[i], bufferB[i + 1] }, 1, 2), System.Globalization.NumberStyles.HexNumber).ToString();
            i = pointer + extra_EXPOffset;
            txtbXexp.Text = Int32.Parse(Swap_Bytes(new byte[] { bufferB[i], bufferB[i + 1] }, 1, 2), System.Globalization.NumberStyles.HexNumber).ToString();

            i = pointer + elemDefOffset;
            Set_TrB_Value(bufferB[i], tbFire, lblEleFire); i++;
            Set_TrB_Value(bufferB[i], tbIce, lblEIce); i++;
            Set_TrB_Value(bufferB[i], tbThunder, lblEThunder); i++;
            Set_TrB_Value(bufferB[i], tbEarth, lblEEarth); i++;
            Set_TrB_Value(bufferB[i], tbPoison, lblEPoison); i++;
            Set_TrB_Value(bufferB[i], tbWind, lblEWind); i++;
            Set_TrB_Value(bufferB[i], tbWater, lblEWater); i++;
            Set_TrB_Value(bufferB[i], tbHoly, lblEHoly);

            i = pointer + high_lvlOffset;
            nudHighStart.Value = bufferB[i];
            i = pointer + med_lvlOffset;
            nudMedStart.Value = bufferB[i];

            //Load all statuses
            i = pointer + statusDefOffset;
            txtbStDeath.Text = (bufferB[i] - 100).ToString(); i++;
            txtbStPoison.Text = (bufferB[i] - 100).ToString(); i++;
            txtbStPetrify.Text = (bufferB[i] - 100).ToString(); i++;
            txtbStBlind.Text = (bufferB[i] - 100).ToString(); i++;
            txtbStSilence.Text = (bufferB[i] - 100).ToString(); i++;
            txtbStBerserk.Text = (bufferB[i] - 100).ToString(); i++;
            txtbStZombie.Text = (bufferB[i] - 100).ToString(); i++;
            txtbStSleep.Text = (bufferB[i] - 100).ToString(); i++;
            txtbStHaste.Text = (bufferB[i] - 100).ToString(); i++;
            txtbStSlow.Text = (bufferB[i] - 100).ToString(); i++;
            txtbStStop.Text = (bufferB[i] - 100).ToString(); i++;
            txtbStRegen.Text = (bufferB[i] - 100).ToString(); i++;
            txtbStReflect.Text = (bufferB[i] - 100).ToString(); i++;
            txtbStDoom.Text = (bufferB[i] - 100).ToString(); i++;
            txtbStPetrCount.Text = (bufferB[i] - 100).ToString(); i++;
            txtbStFloat.Text = (bufferB[i] - 100).ToString(); i++;
            txtbStConfu.Text = (bufferB[i] - 100).ToString(); i++;
            txtbStDrain.Text = (bufferB[i] - 100).ToString(); i++;
            txtbStVit0.Text = (bufferB[i] - 100).ToString(); i++;
            txtbStPercent.Text = (bufferB[i] - 100).ToString();

            double mRate = bufferB[pointer + mugRateOffset] * 100 / 256;
            double dRate = bufferB[pointer + dropRateOffset] * 100 / 256;
            txtbMugRate.Text = mRate.ToString();
            txtbDropRate.Text = dRate.ToString();

            i = pointer + low_lvlMugOffset;
            cbMugLow1.SelectedIndex = bufferB[i]; i++;
            nudMugLow1.Value = bufferB[i]; i++;
            cbMugLow2.SelectedIndex = bufferB[i]; i++;
            nudMugLow2.Value = bufferB[i]; i++;
            cbMugLow3.SelectedIndex = bufferB[i]; i++;
            nudMugLow3.Value = bufferB[i]; i++;
            cbMugLow4.SelectedIndex = bufferB[i]; i++;
            nudMugLow4.Value = bufferB[i];

            i = pointer + med_lvlMugOffset;
            cbMugMed1.SelectedIndex = bufferB[i]; i++;
            nudMugMed1.Value = bufferB[i]; i++;
            cbMugMed2.SelectedIndex = bufferB[i]; i++;
            nudMugMed2.Value = bufferB[i]; i++;
            cbMugMed3.SelectedIndex = bufferB[i]; i++;
            nudMugMed3.Value = bufferB[i]; i++;
            cbMugMed4.SelectedIndex = bufferB[i]; i++;
            nudMugMed4.Value = bufferB[i];

            i = pointer + high_lvlMugOffset;
            cbMugHigh1.SelectedIndex = bufferB[i]; i++;
            nudMugHigh1.Value = bufferB[i]; i++;
            cbMugHigh2.SelectedIndex = bufferB[i]; i++;
            nudMugHigh2.Value = bufferB[i]; i++;
            cbMugHigh3.SelectedIndex = bufferB[i]; i++;
            nudMugHigh3.Value = bufferB[i]; i++;
            cbMugHigh4.SelectedIndex = bufferB[i]; i++;
            nudMugHigh4.Value = bufferB[i];

            i = pointer + low_lvlDropOffset;
            cbDropLow1.SelectedIndex = bufferB[i]; i++;
            nudDropLow1.Value = bufferB[i]; i++;
            cbDropLow2.SelectedIndex = bufferB[i]; i++;
            nudDropLow2.Value = bufferB[i]; i++;
            cbDropLow3.SelectedIndex = bufferB[i]; i++;
            nudDropLow3.Value = bufferB[i]; i++;
            cbDropLow4.SelectedIndex = bufferB[i]; i++;
            nudDropLow4.Value = bufferB[i];

            i = pointer + med_lvlDropOffset;
            cbDropMed1.SelectedIndex = bufferB[i]; i++;
            nudDropMed1.Value = bufferB[i]; i++;
            cbDropMed2.SelectedIndex = bufferB[i]; i++;
            nudDropMed2.Value = bufferB[i]; i++;
            cbDropMed3.SelectedIndex = bufferB[i]; i++;
            nudDropMed3.Value = bufferB[i]; i++;
            cbDropMed4.SelectedIndex = bufferB[i]; i++;
            nudDropMed4.Value = bufferB[i];

            i = pointer + high_lvlDropOffset;
            cbDropHigh1.SelectedIndex = bufferB[i]; i++;
            nudDropHigh1.Value = bufferB[i]; i++;
            cbDropHigh2.SelectedIndex = bufferB[i]; i++;
            nudDropHigh2.Value = bufferB[i]; i++;
            cbDropHigh3.SelectedIndex = bufferB[i]; i++;
            nudDropHigh3.Value = bufferB[i]; i++;
            cbDropHigh4.SelectedIndex = bufferB[i]; i++;
            nudDropHigh4.Value = bufferB[i];

            i = pointer + low_lvlMagOffset;
            cbDrawLow1.SelectedIndex = bufferB[i]; i++;
            nudDrawLow1.Value = bufferB[i]; i++;
            cbDrawLow2.SelectedIndex = bufferB[i]; i++;
            nudDrawLow2.Value = bufferB[i]; i++;
            cbDrawLow3.SelectedIndex = bufferB[i]; i++;
            nudDrawLow3.Value = bufferB[i]; i++;
            cbDrawLow4.SelectedIndex = bufferB[i]; i++;
            nudDrawLow4.Value = bufferB[i];

            i = pointer + med_lvlMagOffset;
            cbDrawMed1.SelectedIndex = bufferB[i]; i++;
            nudDrawMed1.Value = bufferB[i]; i++;
            cbDrawMed2.SelectedIndex = bufferB[i]; i++;
            nudDrawMed2.Value = bufferB[i]; i++;
            cbDrawMed3.SelectedIndex = bufferB[i]; i++;
            nudDrawMed3.Value = bufferB[i]; i++;
            cbDrawMed4.SelectedIndex = bufferB[i]; i++;
            nudDrawMed4.Value = bufferB[i];

            i = pointer + high_lvlMagOffset;
            cbDrawHigh1.SelectedIndex = bufferB[i]; i++;
            nudDrawHigh1.Value = bufferB[i]; i++;
            cbDrawHigh2.SelectedIndex = bufferB[i]; i++;
            nudDrawHigh2.Value = bufferB[i]; i++;
            cbDrawHigh3.SelectedIndex = bufferB[i]; i++;
            nudDrawHigh3.Value = bufferB[i]; i++;
            cbDrawHigh4.SelectedIndex = bufferB[i]; i++;
            nudDrawHigh4.Value = bufferB[i];

            i = pointer + devourOffset;
            cbDevourLow.SelectedIndex = bufferB[i]; i++;
            cbDevourMed.SelectedIndex = bufferB[i]; i++;
            cbDevourHigh.SelectedIndex = bufferB[i];

            i = pointer + cardOffset;
            cbCardLow.SelectedIndex = bufferB[i]; i++;
            cbCardMed.SelectedIndex = bufferB[i]; i++;
            cbCardHigh.SelectedIndex = bufferB[i];

            //Load all flag values.
            foreach (Control c in gbFlags.Controls)
            {
                if (c is CheckBox)
                {
                    string[] tag = (c as CheckBox).Tag.ToString().Split(new char[] { ';' });
                    int offset = pointer + Int32.Parse(tag[0]);
                    int value = Byte.Parse(tag[1]);
                    value = bufferB[offset] & value;
                    (c as CheckBox).Checked = (value > 0);
                }
            }

            //Load all unknown Values.
            foreach (Control p in flowLayoutPanelUnknowns.Controls)
            {
                if (p is Panel)
                {
                    foreach (Control n in p.Controls)
                    {
                        if (n is NumericUpDown)
                            (n as NumericUpDown).Value = bufferB[pointer + (int)(n as NumericUpDown).Tag];
                    }
                }
            }

            //Create abilities
            for (int ii = 0; ii < abilities.Length; ii++)
            {
                int o = abilities[ii].startOffset = pointer + abilitiesOffset + ii * 4;
                abilities[ii].kernelID = (KernelID)bufferB[o];
                abilities[ii].unknown = bufferB[o + 1];
                abilities[ii].abilityID = UInt16.Parse(Swap_Bytes(new byte[] { bufferB[o + 2], bufferB[o + 3] }, 1, 2), System.Globalization.NumberStyles.HexNumber);
            }
            FillAbilitiesFlowPanel(flowLayoutPanel1);
            FillAbilitiesFlowPanel(flowLayoutPanel2);
            FillAbilitiesFlowPanel(flowLayoutPanel3);

            validate = true;
            #endregion

            GRegistry.SetRegValue(regKey, "initial_dir", filePath, RegistryValueKind.String);

            tmiSave.Enabled = false;
            tsbSave.Enabled = false;
            tslbl2.Text = "       -";

            fileOpen = true;
            if (reOpenToolWin)
            {
                if (rStats.IsDisposed || rStats == null)
                {
                    rStats = new Report(eName, this);
                    rStats.Show(this);
                }
                else
                    rStats.Text = eName + ": Stat points pr. lvl.";
                Calc_GridView(rStats.Get_GridView(), rStats.Get_Level_Inc(), rStats.Get_Avg_Level(), rStats.Get_F_Level());
                this.Focus();
            }
            return res;
        }

        private void FillAbilitiesFlowPanel(FlowLayoutPanel flp)
        {
            foreach (Control c in flp.Controls)
            {
                int i = Int32.Parse("" + c.Tag);
                foreach (Control cc in c.Controls)
                {
                    int j = Int32.Parse("" + cc.Tag);
                    if (j == 0) (cc as ComboBox).SelectedItem = abilities[i].kernelID;
                    else if (j == 1) (cc as NumericUpDown).Value = abilities[i].unknown;
                    else if (j == 2) (cc as NumericUpDown).Value = abilities[i].abilityID;
                    j.ToString();
                }
            }
        }

        private void Main_DragDrop(object sender, DragEventArgs e)
        {
            try
            {
                this.SuspendLayout();
                Array a = (Array)e.Data.GetData(DataFormats.FileDrop);
                if (a != null)
                {
                    fileSave = fileName;
                    fileName = filePath = a.GetValue(0).ToString();
                    Do_Open();
                }
            }
            catch (Exception ex)
            {
                tslbl2.Text = ex.Message;
            }
            finally
            {
                this.ResumeLayout(false);
                this.PerformLayout();
            }

        }
        private void Main_DragEnter(object sender, DragEventArgs e)
        {
            if (e.Data.GetDataPresent(DataFormats.FileDrop, false) == true)
            {
                e.Effect = DragDropEffects.Copy;

            }
            else
                e.Effect = DragDropEffects.None;
        }

        #endregion

        #region Help Methods

        private string Make_Enemy_Name(byte b)
        {
            string s = "";
            int i;
            hexValue = b.ToString("x").ToUpper();
            hexValue = hexValue.ToUpper();
            i = textFormat.IndexOf(hexValue) + 3;
            s = textFormat.Substring(i);
            if (s.Contains("\r"))
            {
                i = s.IndexOf("\r");
                s = s.Remove(i);
            }

            return s;
        }
        private void Check_Tool_Text()
        {
            if (tslblPath.Text.Length > 72)
            {
                tslblPath.Text = tslblPath.Text.Remove(70);
                tslblPath.Text += "...";
            }
        }
        private string Swap_Bytes(byte[] b, int startOffset, short bytesToSwap)
        {
            string s = "";
            hexValue = "";
            for (int i = startOffset; i > (startOffset - bytesToSwap); i--)
            {
                s = b[i].ToString("x");
                if (s.Length < 2)
                    s = "0" + s;
                hexValue += s;
            }
            while (hexValue.StartsWith("0"))
            {
                hexValue = hexValue.TrimStart('0');
            }
            if (hexValue == "")
                return "0";
            return hexValue;
        }
        private void Bad_File()
        {
            MessageBox.Show(this, BadFile, "Error", MessageBoxButtons.OK, MessageBoxIcon.Stop);
            fileStream.Close();
        }
        public void Exit()
        {
            try
            {
                fileStream.Dispose();
                File.Delete(".\\temp.txt");
            }
            catch (Exception ex) { tslbl2.Text = ex.Message; }
            Application.Exit();
        }
        private void Enable_Save()
        {
            if (fileOpen)
            {

                string x;
                string z;
                bool b = false;
                for (int i = pointer; i < (pointer + statusDefOffset + 0x20); i++)
                {
                    x = bufferB.GetValue(i).ToString();
                    z = bufferBCopy.GetValue(i).ToString();
                    if (x != z)
                    {
                        b = true;
                        break;
                    }
                }
                if (b)
                {
                    if (!this.Text.EndsWith("*"))
                        this.Text += "*";
                    tsbSave.Enabled = true;
                    tmiSave.Enabled = true;
                }
                else
                {
                    this.Text = this.Text.TrimEnd('*');
                    tsbSave.Enabled = false;
                    tmiSave.Enabled = false;
                    tslbl2.Text = "       -";
                }
            }
        }
        private void NValue_Changed(object sender, EventArgs e)
        {
            SetOffsetValue(pointer + med_lvlOffset, (int)nudMedStart.Value);
            SetOffsetValue(pointer + high_lvlOffset, (int)nudHighStart.Value);
            lblLowlvls.Text = "0 <> " + (nudMedStart.Value - 1).ToString();
            lblMedlvls.Text = nudMedStart.Value.ToString() + " <> " + (nudHighStart.Value - 1).ToString();
            lblHighlvls.Text = nudHighStart.Value.ToString() + " <> 100";
        }
        private void Text_Validating(object sender, CancelEventArgs e)
        {
            enableSave = false;
            try
            {
                if (validate)
                {
                    if (txtbName.TextLength >= 25)
                        txtbName.Text = txtbName.Text.Remove(24);

                    CT(txtbEva1, 0, 255);
                    CT(txtbEva2, 1, 255);
                    CT(txtbEva3, 0, 255);
                    CT(txtbEva4, 1, 255);

                    CT(txtbStr1, 0, 255);
                    CT(txtbStr2, 1, 255);
                    CT(txtbStr3, 0, 255);
                    CT(txtbStr4, 1, 255);

                    CT(txtbVit1, 0, 255);
                    CT(txtbVit2, 1, 255);
                    CT(txtbVit3, 0, 255);
                    CT(txtbVit4, 1, 255);

                    CT(txtbMag1, 0, 255);
                    CT(txtbMag2, 1, 255);
                    CT(txtbMag3, 0, 255);
                    CT(txtbMag4, 1, 255);

                    CT(txtbSpr1, 0, 255);
                    CT(txtbSpr2, 1, 255);
                    CT(txtbSpr3, 0, 255);
                    CT(txtbSpr4, 1, 255);

                    CT(txtbSpd1, 0, 255);
                    CT(txtbSpd2, 1, 255);
                    CT(txtbSpd3, 0, 255);
                    CT(txtbSpd4, 1, 255);

                    CT(txtbHP1, 0, 255);
                    CT(txtbHP2, 0, 255);
                    CT(txtbHP3, 0, 255);
                    CT(txtbHP4, 0, 255);

                    CT(txtbEXP, 0, 65535);
                    CT(txtbXexp, 0, 65535);
                    CT(txtbAP, 0, 255);

                    CT(txtbStDeath, 0, 155);
                    CT(txtbStPetrify, 0, 155);
                    CT(txtbStPoison, 0, 155);
                    CT(txtbStBlind, 0, 155);
                    CT(txtbStSilence, 0, 155);
                    CT(txtbStBerserk, 0, 155);
                    CT(txtbStZombie, 0, 155);
                    CT(txtbStSleep, 0, 155);
                    CT(txtbStHaste, 0, 155);
                    CT(txtbStSlow, 0, 155);
                    CT(txtbStStop, 0, 155);
                    CT(txtbStRegen, 0, 155);
                    CT(txtbStReflect, 0, 155);
                    CT(txtbStDoom, 0, 155);
                    CT(txtbStPetrCount, 0, 155);
                    CT(txtbStFloat, 0, 155);
                    CT(txtbStConfu, 0, 155);
                    CT(txtbStDrain, 0, 155);
                    CT(txtbStVit0, 0, 155);
                    CT(txtbStPercent, 0, 155);

                    CT(txtbDropRate, 0, 100);
                    CT(txtbMugRate, 0, 100);
                }
                enableSave = true;
            }
            catch (Exception ex)
            {
                activeTxtb.Text = ex.Message;
                activeTxtb.Text = "1";
            }

        }
        private void CT(TextBox tb, ushort minValue, ushort maxValue)
        {
            activeTxtb = tb;
            if (tb.Text == "" || Convert.ToInt32(tb.Text) < minValue)
            {
                tb.Text = minValue.ToString();
                return;
            }
            if (Convert.ToInt32(tb.Text) > maxValue)
                tb.Text = maxValue.ToString();
        }
        private void FT(byte b, TextBox tb)
        {
            tb.Text = b.ToString();
        }
        private void SetOffsetValue(int offset, int tag)
        {
            if (fileOpen)
            {
                bufferB.SetValue((byte)tag, offset);
                fileSave = fileName;
            }
            Enable_Save();

        }
        private void tabControl_Selected(object sender, TabControlEventArgs e)
        {
            txtbName.Parent = e.TabPage;
            label41.Parent = e.TabPage;
        }
        private void Main_FormClosing(object sender, FormClosingEventArgs e)
        {
            if (this.Text.EndsWith("*"))
            {
                res = MessageBox.Show(this, "Save changes?", "Save", MessageBoxButtons.YesNo, MessageBoxIcon.Question, MessageBoxDefaultButton.Button2);

                if (res == DialogResult.Yes)
                    Save_Click(null, new EventArgs());
            }
        }
        public void ReOpenToolWindow(bool open) { reOpenToolWin = open; }
        private void FillCombobox(ComboBox cb, string ifrFile, short endindex)
        {
            int one = cb.Name.Contains("Card") ? 1 : 0;
            if (cb.Name.Contains("Devour")) cb.Items.Add("HP Recovery");
            else if (one != 1) cb.Items.Add("Nothing");
            string s = "";
            int stringPos = 0;
            for (int i = 1 - one; i < endindex + 1; i++)
            {
                s = (i + one).ToString("x").ToUpper();
                stringPos = ifrFile.IndexOf("\r\n" + s + "<");
                if ((i + one) < 16)
                    s = ifrFile.Substring(stringPos + 4);
                else if (i == 255)
                    s = "Immune";
                else if (one == 1 && i > 109)
                    s = "??? 0x" + i.ToString("x");
                else
                    s = ifrFile.Substring(stringPos + 5);
                if (s.Contains("\r"))
                {
                    stringPos = s.IndexOf("\r\n");
                    s = s.Remove(stringPos);
                }
                cb.Items.Add(s);
            }
        }

        #endregion

        #region Track Bars

        private void Set_TrB_Value(byte b, TrackBar trb, Label lbl)
        {
            int value = 900 - b * 10;
            lbl.Text = value.ToString() + "%";
            trb.Value = b;
        }
        private void tbFire_Scroll(object sender, EventArgs e)
        {
            SetOffsetValue(pointer + elemDefOffset, tbFire.Value);
            lblEleFire.Text = (900 - tbFire.Value * 10).ToString() + "%";
        }
        private void tbThunder_Scroll(object sender, EventArgs e)
        {
            SetOffsetValue(pointer + elemDefOffset + 2, tbThunder.Value);
            lblEThunder.Text = (900 - tbThunder.Value * 10).ToString() + "%";
        }
        private void tbWater_Scroll(object sender, EventArgs e)
        {
            SetOffsetValue(pointer + elemDefOffset + 6, tbWater.Value);
            lblEWater.Text = (900 - tbWater.Value * 10).ToString() + "%";
        }
        private void tbPoison_Scroll(object sender, EventArgs e)
        {
            SetOffsetValue(pointer + elemDefOffset + 4, tbPoison.Value);
            lblEPoison.Text = (900 - tbPoison.Value * 10).ToString() + "%";
        }
        private void tbIce_Scroll(object sender, EventArgs e)
        {
            SetOffsetValue(pointer + elemDefOffset + 1, tbIce.Value);
            lblEIce.Text = (900 - tbIce.Value * 10).ToString() + "%";
        }
        private void tbEarth_Scroll(object sender, EventArgs e)
        {
            SetOffsetValue(pointer + elemDefOffset + 3, tbEarth.Value);
            lblEEarth.Text = (900 - tbEarth.Value * 10).ToString() + "%";
        }
        private void tbWind_Scroll(object sender, EventArgs e)
        {
            SetOffsetValue(pointer + elemDefOffset + 5, tbWind.Value);
            lblEWind.Text = (900 - tbWind.Value * 10).ToString() + "%";
        }
        private void tbHoly_Scroll(object sender, EventArgs e)
        {
            SetOffsetValue(pointer + elemDefOffset + 7, tbHoly.Value);
            lblEHoly.Text = (900 - tbHoly.Value * 10).ToString() + "%";
        }

        #endregion

        #region Text Boxes

        private void TB_KeyPress(object sender, KeyEventArgs e)
        {
            try
            {
                int i = 0;
                if (((TextBox)sender).Text != "")
                    i = Convert.ToInt32(((TextBox)sender).Text);
                if (e.KeyData == Keys.Up)
                    i++;
                else if (e.KeyData == Keys.Down && i > 0)
                    i--;
                ((TextBox)sender).Text = i + "";
                Text_Validating(sender, new CancelEventArgs());
            }
            catch (Exception ex) { ex.GetType(); }
        }

        private void Name_Value_Changed(object sender, EventArgs e)
        {
            if (txtbName.Text.Contains("\\"))
                txtbName.Text = txtbName.Text.Replace("\\", "");
            if (txtbName.Text.Contains(";"))
                txtbName.Text = txtbName.Text.Replace(";", "");
            if (fileOpen && txtbName.TextLength > 0)
            {
                try
                {
                    Text_Validating(sender, new CancelEventArgs());
                    int j = 0;
                    int i = 0;
                    int k = 0;
                    char c = ' ';
                    string s = "";
                    string t = "";
                    //string b = "";
                    label41.Text = "Real name: ";
                    for (i = 0; i < 25; i++)
                    {

                        //b = bufferBCopy[i + pointer + nameOffset].ToString("x");
                        //if (!textFormat.Contains(b + "="))
                        //{
                        //    bufferB.SetValue(b, i + pointer + nameOffset);
                        //    continue;
                        //}
                        if (i < txtbName.TextLength)
                        {
                            c = txtbName.Text[k];
                            k++;
                        }
                        else if (i >= txtbName.TextLength)
                        {
                            if (i < 24)
                                bufferB.SetValue((byte)0, i + pointer + nameOffset);
                            else
                                bufferB.SetValue(bufferBCopy[i + pointer + nameOffset], i + pointer + nameOffset);
                            continue;
                        }
                        else if (!textFormat.Contains(c.ToString() + "\r"))
                        {
                            if (i < txtbName.TextLength)
                                bufferB.SetValue(bufferBCopy[i + pointer + nameOffset], i + pointer + nameOffset);
                            continue;
                        }

                        j = textFormat.IndexOf((c + "\r"), 4) - 3;
                        t = textFormat.Substring(j + 3);
                        t = t.Remove(1);
                        label41.Text += t;
                        if (t == "]")
                            s = "AA";
                        else if (t == ".")
                            s = "3B";
                        else if (t == "\"")
                            s = "3F";
                        else
                        {
                            s = textFormat.Substring(j);
                            s = s.Remove(2);
                        }

                        bufferB.SetValue(Byte.Parse(s, System.Globalization.NumberStyles.HexNumber), i + pointer + nameOffset);
                    }
                    fileSave = fileName;
                    Enable_Save();
                }
                catch (Exception ex)
                {
                    tslbl2.Text = ex.Message;
                    //MessageBox.Show(ex.Message);
                }
            }
        }
        private void HP_Changed(object sender, EventArgs e)
        {
            if (!fileOpen)
                return;
            Text_Validating(sender, new CancelEventArgs());
            try
            {
                SetOffsetValue(pointer + hp_b1Offset, Convert.ToInt32(txtbHP1.Text));
                SetOffsetValue(pointer + hp_b1Offset + 1, Convert.ToInt32(txtbHP2.Text));
                SetOffsetValue(pointer + hp_b1Offset + 2, Convert.ToInt32(txtbHP3.Text));
                SetOffsetValue(pointer + hp_b1Offset + 3, Convert.ToInt32(txtbHP4.Text));
                if (reOpenToolWin)
                    Calc_GridView(rStats.Get_GridView(), rStats.Get_Level_Inc(), rStats.Get_Avg_Level(), rStats.Get_F_Level());
            }
            catch (Exception ex)
            {
                MessageBox.Show(ex.Message);
            }
        }
        private void Str_Changed(object sender, EventArgs e)
        {
            if (!fileOpen)
                return;
            Text_Validating(sender, new CancelEventArgs());
            try
            {
                SetOffsetValue(pointer + str_b1Offset, Convert.ToInt32(txtbStr1.Text));
                SetOffsetValue(pointer + str_b1Offset + 1, Convert.ToInt32(txtbStr2.Text));
                SetOffsetValue(pointer + str_b1Offset + 2, Convert.ToInt32(txtbStr3.Text));
                SetOffsetValue(pointer + str_b1Offset + 3, Convert.ToInt32(txtbStr4.Text));
                if (reOpenToolWin)
                    Calc_GridView(rStats.Get_GridView(), rStats.Get_Level_Inc(), rStats.Get_Avg_Level(), rStats.Get_F_Level());
            }
            catch (Exception ex)
            {
                MessageBox.Show(ex.Message);
            }
        }
        private void Mag_Changed(object sender, EventArgs e)
        {
            if (!fileOpen)
                return;
            Text_Validating(sender, new CancelEventArgs());
            try
            {
                SetOffsetValue(pointer + mag_b1Offset, Convert.ToInt32(txtbMag1.Text));
                SetOffsetValue(pointer + mag_b1Offset + 1, Convert.ToInt32(txtbMag2.Text));
                SetOffsetValue(pointer + mag_b1Offset + 2, Convert.ToInt32(txtbMag3.Text));
                SetOffsetValue(pointer + mag_b1Offset + 3, Convert.ToInt32(txtbMag4.Text));
                if (reOpenToolWin)
                    Calc_GridView(rStats.Get_GridView(), rStats.Get_Level_Inc(), rStats.Get_Avg_Level(), rStats.Get_F_Level());
            }
            catch (Exception ex)
            {
                MessageBox.Show(ex.Message);
            }
        }
        private void Vit_Changed(object sender, EventArgs e)
        {
            if (!fileOpen)
                return;
            Text_Validating(sender, new CancelEventArgs());
            try
            {
                SetOffsetValue(pointer + vit_b1Offset, Convert.ToInt32(txtbVit1.Text));
                SetOffsetValue(pointer + vit_b1Offset + 1, Convert.ToInt32(txtbVit2.Text));
                SetOffsetValue(pointer + vit_b1Offset + 2, Convert.ToInt32(txtbVit3.Text));
                SetOffsetValue(pointer + vit_b1Offset + 3, Convert.ToInt32(txtbVit4.Text));
                if (reOpenToolWin)
                    Calc_GridView(rStats.Get_GridView(), rStats.Get_Level_Inc(), rStats.Get_Avg_Level(), rStats.Get_F_Level());
            }
            catch (Exception ex)
            {
                MessageBox.Show(ex.Message);
            }
        }
        private void Spr_Changed(object sender, EventArgs e)
        {
            if (!fileOpen)
                return;
            Text_Validating(sender, new CancelEventArgs());
            try
            {
                SetOffsetValue(pointer + spr_b1Offset, Convert.ToInt32(txtbSpr1.Text));
                SetOffsetValue(pointer + spr_b1Offset + 1, Convert.ToInt32(txtbSpr2.Text));
                SetOffsetValue(pointer + spr_b1Offset + 2, Convert.ToInt32(txtbSpr3.Text));
                SetOffsetValue(pointer + spr_b1Offset + 3, Convert.ToInt32(txtbSpr4.Text));
                if (reOpenToolWin)
                    Calc_GridView(rStats.Get_GridView(), rStats.Get_Level_Inc(), rStats.Get_Avg_Level(), rStats.Get_F_Level());
            }
            catch (Exception ex)
            {
                MessageBox.Show(ex.Message);
            }
        }
        private void Spd_Changed(object sender, EventArgs e)
        {
            if (!fileOpen)
                return;
            Text_Validating(sender, new CancelEventArgs());
            try
            {
                SetOffsetValue(pointer + spd_b1Offset, Convert.ToInt32(txtbSpd1.Text));
                SetOffsetValue(pointer + spd_b1Offset + 1, Convert.ToInt32(txtbSpd2.Text));
                SetOffsetValue(pointer + spd_b1Offset + 2, Convert.ToInt32(txtbSpd3.Text));
                SetOffsetValue(pointer + spd_b1Offset + 3, Convert.ToInt32(txtbSpd4.Text));
                if (reOpenToolWin)
                    Calc_GridView(rStats.Get_GridView(), rStats.Get_Level_Inc(), rStats.Get_Avg_Level(), rStats.Get_F_Level());
            }
            catch (Exception ex)
            {
                MessageBox.Show(ex.Message);
            }
        }
        private void Eva_Changed(object sender, EventArgs e)
        {
            if (!fileOpen)
                return;
            Text_Validating(sender, new CancelEventArgs());
            try
            {
                SetOffsetValue(pointer + eva_b1Offset, Convert.ToInt32(txtbEva1.Text));
                SetOffsetValue(pointer + eva_b1Offset + 1, Convert.ToInt32(txtbEva2.Text));
                SetOffsetValue(pointer + eva_b1Offset + 2, Convert.ToInt32(txtbEva3.Text));
                SetOffsetValue(pointer + eva_b1Offset + 3, Convert.ToInt32(txtbEva4.Text));
                if (reOpenToolWin)
                    Calc_GridView(rStats.Get_GridView(), rStats.Get_Level_Inc(), rStats.Get_Avg_Level(), rStats.Get_F_Level());
            }
            catch (Exception ex)
            {
                MessageBox.Show(ex.Message);
            }
        }
        private void AP_Changed(object sender, EventArgs e)
        {
            if (!fileOpen)
                return;
            Text_Validating(sender, new CancelEventArgs());
            try
            {
                SetOffsetValue(pointer + apOffset, Convert.ToInt32(txtbAP.Text));
            }
            catch (Exception ex)
            {
                MessageBox.Show(ex.Message);
            }
        }
        private void Exp_Changed(object sender, EventArgs e)
        {
            if (!fileOpen)
                return;
            Text_Validating(sender, new CancelEventArgs());
            try
            {
                string s = Make_Into_Offset(txtbXexp.Text);
                if (s.Length > 2)
                    Store_EXP(s, pointer + extra_EXPOffset);
                else
                {
                    SetOffsetValue(pointer + extra_EXPOffset, Convert.ToByte(txtbXexp.Text));
                    SetOffsetValue(pointer + extra_EXPOffset + 1, 0);
                }
                s = Make_Into_Offset(txtbEXP.Text);
                if (s.Length > 2)
                    Store_EXP(s, pointer + EXP_Offset);
                else
                {
                    SetOffsetValue(pointer + EXP_Offset, Convert.ToByte(txtbEXP.Text));
                    SetOffsetValue(pointer + EXP_Offset + 1, 0);
                }
                if (reOpenToolWin)
                    Calc_GridView(rStats.Get_GridView(), rStats.Get_Level_Inc(), rStats.Get_Avg_Level(), rStats.Get_F_Level());
            }
            catch (Exception ex)
            {
                MessageBox.Show(ex.Message);
            }
        }
        private string Make_Into_Offset(string s)
        {

            s = Convert.ToInt32(s).ToString("x");
            if (s.Length % 2 != 0)
                s = "0" + s;
            return s;
        }
        private void Store_EXP(string s, int offset)
        {
            int b1 = Int32.Parse(s.Remove(2), System.Globalization.NumberStyles.HexNumber);
            int b2 = Int32.Parse(s.Substring(2), System.Globalization.NumberStyles.HexNumber);
            SetOffsetValue(offset, b2);
            SetOffsetValue(offset + 1, b1);
        }
        private void Status_Changed(object sender, EventArgs e)
        {
            if (!fileOpen)
                return;
            Text_Validating(sender, new CancelEventArgs());
            try
            {
                int i = pointer + statusDefOffset;
                SetOffsetValue(i, Convert.ToInt32(txtbStDeath.Text) + 100);
                SetOffsetValue(i + 1, Convert.ToInt32(txtbStPoison.Text) + 100);
                SetOffsetValue(i + 2, Convert.ToInt32(txtbStPetrify.Text) + 100);
                SetOffsetValue(i + 3, Convert.ToInt32(txtbStBlind.Text) + 100);
                SetOffsetValue(i + 4, Convert.ToInt32(txtbStSilence.Text) + 100);
                SetOffsetValue(i + 5, Convert.ToInt32(txtbStBerserk.Text) + 100);
                SetOffsetValue(i + 6, Convert.ToInt32(txtbStZombie.Text) + 100);
                SetOffsetValue(i + 7, Convert.ToInt32(txtbStSleep.Text) + 100);
                SetOffsetValue(i + 8, Convert.ToInt32(txtbStHaste.Text) + 100);
                SetOffsetValue(i + 9, Convert.ToInt32(txtbStSlow.Text) + 100);
                SetOffsetValue(i + 10, Convert.ToInt32(txtbStStop.Text) + 100);
                SetOffsetValue(i + 11, Convert.ToInt32(txtbStRegen.Text) + 100);
                SetOffsetValue(i + 12, Convert.ToInt32(txtbStReflect.Text) + 100);
                SetOffsetValue(i + 13, Convert.ToInt32(txtbStDoom.Text) + 100);
                SetOffsetValue(i + 14, Convert.ToInt32(txtbStPetrCount.Text) + 100);
                SetOffsetValue(i + 15, Convert.ToInt32(txtbStFloat.Text) + 100);
                SetOffsetValue(i + 16, Convert.ToInt32(txtbStConfu.Text) + 100);
                SetOffsetValue(i + 17, Convert.ToInt32(txtbStDrain.Text) + 100);
                SetOffsetValue(i + 18, Convert.ToInt32(txtbStVit0.Text) + 100);
                SetOffsetValue(i + 19, Convert.ToInt32(txtbStPercent.Text) + 100);
            }
            catch (Exception ex)
            {
                MessageBox.Show(ex.Message);
            }
        }
        #endregion

        #region Stat Calculation

        /// <summary>
        /// Calculates HP.
        /// </summary>
        /// <param name="x">The enemy's level.</param>
        /// <returns></returns>
        public int CalcHP(double x)
        {
            double retValue = 0;
            double hp_1 = Convert.ToDouble(txtbHP1.Text);
            double hp_2 = Convert.ToDouble(txtbHP2.Text);
            double hp_3 = Convert.ToDouble(txtbHP3.Text);
            double hp_4 = Convert.ToDouble(txtbHP4.Text);
            retValue = (hp_1 * x * x / 20.0) + (hp_1 + hp_3 * 100.0) * x + hp_2 * 10.0 + hp_4 * 1000.0;

            return Convert.ToInt32(retValue);
        }
        /// <summary>
        /// Calculates the basic stats
        /// </summary>
        /// <param name="x">The enemy's level.</param>
        /// <param name="tb1">The 1st value.</param>
        /// <param name="tb2">The 2nd value.</param>
        /// <param name="tb3">The 3rd value.</param>
        /// <param name="tb4">The 4th value.</param>
        /// <param name="strOrMag">Shall str or mag be calculated?</param>
        /// <returns></returns>
        public int CalcSTR_MAG_VIT_SPR_SPD_Or_EVA(double x, TextBox tb1, TextBox tb2, TextBox tb3, TextBox tb4, bool strOrMag)
        {
            double retValue = 0;

            double str_1 = Convert.ToDouble(tb1.Text);
            double str_2 = Convert.ToDouble(tb2.Text);
            double str_3 = Convert.ToDouble(tb3.Text);
            double str_4 = Convert.ToDouble(tb4.Text);

            if (strOrMag)
                ////         (x * str_1 / 10 + x / str_2 - x * x / 2 / str_4 + str_3) / 4
                retValue = (x * str_1 / 10.0 + x / str_2 - x * x / 2.0 / str_4 + str_3) / 4.0;
            else
                retValue = (x / str_2) - (x / str_4) + (x * str_1) + str_3;
            retValue = retValue < 0 ? 0 : retValue;
            retValue = retValue > 255 ? 255 : retValue;
            return Convert.ToInt32(retValue);
        }
        /// <summary>
        /// Calculates either the exp recieved or the extra exp recieved to the character that finshed the enemy.
        /// </summary>
        /// <param name="x">The enemy's level</param>
        /// <param name="cLevel">if 'finished' is 'true' then this is the character that finished the enemy level.
        /// Else it's the average party level.</param>
        /// <param name="finished">Are the previous parameter the character that finihsed the enemy level.
        /// If not the second parameter is the avarage part level.</param>
        /// <returns></returns>
        public int CalcEXP_Or_XEXP(double x, double cLevel, bool finished)
        {
            double retValue = 0;
            if (!finished)
            {
                double exp_value = Convert.ToDouble(txtbEXP.Text);
                retValue = exp_value * (5.0 * (x - cLevel) / cLevel + 4.0);
            }
            else
            {
                double exp_value = Convert.ToDouble(txtbXexp.Text);
                retValue = exp_value * (5.0 * (x - cLevel) / cLevel + 4.0);
            }
            retValue = retValue < 0 ? 0 : retValue;
            return Convert.ToInt32(retValue);
        }

        public void Calc_GridView(DataGridView gw, short lvlPrRow, double avgPtyLvl, double fCharLvl)
        {
            avgPtyLvl++;
            fCharLvl++;
            if (!fileOpen)
                return;
            if (lvlPrRow < 1 || lvlPrRow > 100)
                lvlPrRow = 1;
            if (avgPtyLvl < 1 || avgPtyLvl > 100)
                avgPtyLvl = 1;
            if (fCharLvl < 1 || fCharLvl > 100)
                fCharLvl = 1;
            short row = 0;
            try
            {
                gw.Rows.Clear();
                for (double i = 1; i < (100 + lvlPrRow); i += lvlPrRow)
                {
                    if (i > 100)
                        i = 100;
                    gw.Rows.Add(new DataGridViewRow());
                    gw.Rows[row].HeaderCell.Value = "Level" + i;
                    gw.Rows[row].Cells[0].Value = CalcHP(i);
                    gw.Rows[row].Cells[1].Value = CalcSTR_MAG_VIT_SPR_SPD_Or_EVA(i, txtbStr1, txtbStr2, txtbStr3, txtbStr4, true);
                    gw.Rows[row].Cells[2].Value = CalcSTR_MAG_VIT_SPR_SPD_Or_EVA(i, txtbMag1, txtbMag2, txtbMag3, txtbMag4, true);
                    gw.Rows[row].Cells[3].Value = CalcSTR_MAG_VIT_SPR_SPD_Or_EVA(i, txtbVit1, txtbVit2, txtbVit3, txtbVit4, false);
                    gw.Rows[row].Cells[4].Value = CalcSTR_MAG_VIT_SPR_SPD_Or_EVA(i, txtbSpr1, txtbSpr2, txtbSpr3, txtbSpr4, false);
                    gw.Rows[row].Cells[5].Value = CalcSTR_MAG_VIT_SPR_SPD_Or_EVA(i, txtbSpd1, txtbSpd2, txtbSpd3, txtbSpd4, false);
                    gw.Rows[row].Cells[6].Value = CalcSTR_MAG_VIT_SPR_SPD_Or_EVA(i, txtbEva1, txtbEva2, txtbEva3, txtbEva4, false);
                    gw.Rows[row].Cells[7].Value = CalcEXP_Or_XEXP(i, avgPtyLvl, false);
                    gw.Rows[row].Cells[8].Value = CalcEXP_Or_XEXP(i, fCharLvl, true);

                    if (i >= 100)
                        break;
                    row++;
                }
            }
            catch (Exception e)
            {
                MessageBox.Show(e.Message);
            }

        }

        #endregion

        #region Items & Magic

        private void Combobox_SelectedIndexChanged(object sender, EventArgs e)
        {
            try
            {

                if (fileOpen)
                {
                    string s = "";
                    s = Convert.ToString(((ComboBox)sender).Tag);
                    SetOffsetValue(pointer + Convert.ToInt32(s), ((ComboBox)sender).SelectedIndex);
                }
            }
            catch (Exception ex)
            {
                MessageBox.Show(ex.Message);
            }

        }

        private void TextBox_Changed(object sender, EventArgs e)
        {
            try
            {
                if (fileOpen)
                {
                    Text_Validating(null, new CancelEventArgs());
                    string s = "";
                    s = Convert.ToString(((TextBox)sender).Tag);
                    double i = Convert.ToInt64(((TextBox)sender).Text);
                    i /= 100;
                    i *= 256;

                    SetOffsetValue(pointer + Convert.ToInt32(s), (int)i);
                }
            }
            catch (Exception ex)
            {
                MessageBox.Show(ex.Message);
            }
        }
        private void NumberBox_Changed(object sender, EventArgs e)
        {
            try
            {
                if (fileOpen)
                {
                    if (((NumericUpDown)sender).Value < 0 || ((NumericUpDown)sender).Value > 100)
                        ((NumericUpDown)sender).Value = 1;
                    string s = "";
                    s = Convert.ToString(((NumericUpDown)sender).Tag);
                    SetOffsetValue(pointer + Convert.ToInt32(s), (int)((NumericUpDown)sender).Value);
                }
            }
            catch (Exception ex)
            {
                MessageBox.Show(ex.Message);
            }
        }

        #endregion

        #region Misc.

        private void AbilityChange(object sender, EventArgs e)
        {
            if (!fileOpen) return;
            try
            {
                int i = Int32.Parse("" + (sender as Control).Parent.Tag);
                int offset = abilities[i].startOffset;
                if (sender is ComboBox)
                    SetOffsetValue(offset, (int)((byte)(sender as ComboBox).SelectedItem));
                else if (sender is NumericUpDown)
                {
                    uint value = (uint)(sender as NumericUpDown).Value;
                    ushort j = UInt16.Parse("" + (sender as NumericUpDown).Tag);

                    foreach (byte b in Flap_Values(value, j))
                    {
                        SetOffsetValue(offset + j, b); j++;
                    }
                }
            }
            catch (Exception ex)
            {
#if DEBUG
                Console.Write(ex.Message);
#endif
            }
        }

        /// <summary>
        /// Makes an integer value into a memory/pointer value.
        /// </summary>
        /// <param name="value">The value to convert.</param>
        /// <param name="bytes">Desired offset byte length. Include all 00h bytes in the pointer.</param>
        /// <returns>The array containig each byte in the pointer.</returns>
        private byte[] Flap_Values(uint value, ushort bytes)
        {
            string s = Make_Into_Offset(value.ToString()).ToUpper();
            while (s.Length < bytes * 2)
            {
                s = "0" + s;
            }
            string o = s;
            int stringIndex;
            byte[] b = new byte[s.Length / 2];
            for (int i = 0; i < b.Length; i++)
            {
                stringIndex = (b.Length * 2 - 1) - (i * 2) - 1;
                o = s.Substring(stringIndex);
                if (o.Length > 2)
                    o = o.Remove(2);
                b[i] = Byte.Parse(o, NumberStyles.HexNumber);
            }
            return b;
        }

        private void FlagChanged(object sender, EventArgs e)
        {
            if (!fileOpen) return;
            try
            {
                string[] tag = (sender as Control).Tag.ToString().Split(new char[] { ';' });
                int offset = pointer + Int32.Parse(tag[0]);
                int value = bufferB[offset] + ((sender as CheckBox).Checked ? Int32.Parse(tag[1]) : -Int32.Parse(tag[1]));
                value = value > 255 ? 255 : value < 0 ? 0 : value;
                SetOffsetValue(offset, value);
            }
            catch (Exception ex)
            {
#if DEBUG
                Console.Write(ex.Message);
#endif
            }
        }

        private void NudChanged(object sender, EventArgs e)
        {
            if (!fileOpen) return;
            try
            {
                SetOffsetValue(pointer + (int)(sender as NumericUpDown).Tag, (int)(sender as NumericUpDown).Value);
            }
            catch (Exception ex)
            {
#if DEBUG
                Console.Write(ex.Message);
#endif
            }
        }

        protected virtual void SendScreenToReg(RegistryKey key)
        {
            if (this.WindowState != FormWindowState.Maximized)
            {
                GRegistry.SetRegValue(key, this.Name + "_Width_" + (int)this.Font.Size,
                    this.Width, RegistryValueKind.DWord);
                GRegistry.SetRegValue(key, this.Name + "_Height_" + (int)this.Font.Size,
                    this.Height, RegistryValueKind.DWord);
            }
            GRegistry.SetRegValue(key, this.Name + "wstate", this.WindowState, RegistryValueKind.DWord);
        }

        protected virtual void SetFormSizeFromReg(RegistryKey key)
        {
            if ((FormWindowState)GRegistry.GetRegValue(key, this.Name + "wstate", FormWindowState.Normal) == FormWindowState.Maximized)
            {
                this.WindowState = FormWindowState.Maximized;
                return;
            }
            int w = Int32.Parse(GRegistry.GetRegValue(key,
                this.Name + "_Width_" + (int)this.Font.Size, this.Width).ToString());
            int h = Int32.Parse(GRegistry.GetRegValue(key,
                this.Name + "_Height_" + (int)this.Font.Size, this.Height).ToString());
            this.Size = new Size(w, h);
        }

        private void Mouse_Leave(object sender, EventArgs e)
        {
            tslbl2.Text = "       -";
        }
        private void exitToolStripMenuItem_MouseEnter(object sender, EventArgs e)
        {
            tslbl2.Text = "       Exit the application";
        }
        private void tmiSave_MouseEnter(object sender, EventArgs e)
        {
            tslbl2.Text = "       Save opened file.";
        }
        private void tmiOFolder_MouseEnter(object sender, EventArgs e)
        {
            tslbl2.Text = "       Open a folder to fill the list with files.";
        }
        private void tmiOpen_MouseEnter(object sender, EventArgs e)
        {
            tslbl2.Text = "       Open a .dat file from battle.fs.";
        }
        private void tmiHelp_MouseEnter(object sender, EventArgs e)
        {
            tslbl2.Text = "       Open help for the application.";
        }
        private void tmiAbout_MouseEnter(object sender, EventArgs e)
        {
            tslbl2.Text = "       About the application.";
        }
        private void toolStripTextBox1_MouseEnter(object sender, EventArgs e)
        {
            tslbl2.Text = "       Type the path to the folder with the battle.fs files.";
        }
        private void toolStripButton2_MouseEnter(object sender, EventArgs e)
        {
            tslbl2.Text = "       Click to open the chosen directory.";
        }

        private void Main_Resize(object sender, EventArgs e)
        {
            SendScreenToReg(regKey);
        }

        private void splitContainer_SplitterMoved(object sender, SplitterEventArgs e)
        {
            GRegistry.SetRegValue(regKey, "split", splitContainer.SplitterDistance, RegistryValueKind.DWord);

        }

        #endregion

        #region Pack/Extract

        private void tmiExtractOne_Click(object sender, EventArgs e)
        {
            try
            {
                if (extracter == null)
                {
                    extracter = new Porter(regKey);
                    extracter.Text = "Extract Files";
                    if (oss[0])
                        extracter.Icon = this.Icon;
                }
                else
                    extracter.Start();
                extracter.Show();
            }
            catch (Exception ex)
            {
                MessageBox.Show(ex.Message);
            }
        }

        private void tmiPack_Click(object sender, EventArgs e)
        {
            try
            {
                string s, d;

                folderBrowserDialog.Description = "Select source folder that contains battle files to create battle archive from. Not all files must be present. Subfolders are ignored.";
                folderBrowserDialog.SelectedPath = (string)GRegistry.GetRegValue(regKey, "ex_dir", string.Empty);
                if (folderBrowserDialog.ShowDialog() != DialogResult.OK) return;

                s = folderBrowserDialog.SelectedPath;

                if (BattleFileHandler.NrOfDefaultFiles(s + Path.DirectorySeparatorChar) < 1)
                {
                    MessageBox.Show("No battle files found; operation aborted. Do not rename extracted files.");
                    return;
                }

                if (string.IsNullOrEmpty(s))
                {
                    MessageBox.Show("No source path selected; operation aborted.");
                    return;
                }

                folderBrowserDialog.Description = "Select destination folder to create archive in. If not all battle files are present in source folder, this folder must contain the FF8 battle archives.";
                folderBrowserDialog.SelectedPath = (string)GRegistry.GetRegValue(regKey, "pack_dir", string.Empty);
                if (folderBrowserDialog.ShowDialog() != DialogResult.OK) return;

                d = folderBrowserDialog.SelectedPath;

                if (string.IsNullOrEmpty(d))
                {
                    MessageBox.Show("No destination path selected; operation aborted.");
                    return;
                }

                BattleFileHandler.AddDirSeperator(ref s);
                BattleFileHandler.AddDirSeperator(ref d);

                Pack p = new Pack(s, d);
                p.ShowDialog();

                GRegistry.SetRegValue(regKey, "ex_dir", s, RegistryValueKind.String);
                GRegistry.SetRegValue(regKey, "pack_dir", d, RegistryValueKind.String);
            }
            catch (Exception ex)
            {
                MessageBox.Show(ex.Message);
            }
        }

        #endregion

    }
}
