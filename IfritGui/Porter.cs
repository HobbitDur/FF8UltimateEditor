using System;
using System.ComponentModel;
using System.IO;
using System.Windows.Forms;
using Ifrit.Code;
using Microsoft.Win32;

namespace Ifrit
{
    public partial class Porter : Form
    {

        BattleFileHandler BattleFiles;
        RegistryKey key; byte type; int ext = 0, max;
        string smax, dir; string[] selection;
        public Porter(RegistryKey key)
        {
            BattleFiles = new BattleFileHandler();
            this.key = key;
            InitializeComponent();
            Start();
        }

        public void Start()
        {
            this.Focus();

            textBox1.Text = (string)GRegistry.GetRegValue(key, "ex_dir", string.Empty);
            FixTextBox(ref textBox1);

            label3.Text = (string)GRegistry.GetRegValue(key, "pack_dir", string.Empty);
            SetBFPath();
        }

        private void button1_Click(object sender, EventArgs e)
        {
            this.Close();
        }

        private void Porter_FormClosing(object sender, FormClosingEventArgs e)
        {
            if(e.CloseReason == CloseReason.UserClosing)
            {
                e.Cancel = true;
                this.Visible = false;
            }
        }

        #region Extract/Import/Pack

        private void ExtractFile(object fileValue, string dest)
        {

            if (fileValue is int)
                BattleFiles.ExtractBattleFile(dest, (int)fileValue);
            else if (fileValue is string)
                BattleFiles.ExtractBattleFile(dest, (string)fileValue);
            else
                throw new ArgumentException("Unknown type", "fileValue");
        }

        private void ExtractAllInListBox(string dest)
        {
            //BattleFiles.ExtractBattleFiles(dest);
            foreach (string s in listBox1.Items)
            {
                ExtractFile(s, dest);
                ext++;
            }
        }

        #endregion

        private void button3_Click(object sender, EventArgs e)
        {
            try
            {
                if (backgroundWorker.IsBusy)
                    throw new Exception("Wait 'til current operation is finished");
                Start();
            }
            catch (Exception ex)
            {
                MessageBox.Show(ex.Message);
            }
        }

        private void button5_Click(object sender, EventArgs e)
        {
            try
            {
                Work(1);
            }
            catch (Exception ex)
            {
                MessageBox.Show(ex.Message);
            }
        }

        private void button7_Click(object sender, EventArgs e)
        {
            try
            {
                Work(2);
            }
            catch (Exception ex)
            {
                MessageBox.Show(ex.Message);
            }
        }

        private void button4_Click(object sender, EventArgs e)
        {
            try
            {
                if (backgroundWorker.IsBusy)
                    throw new Exception("Wait 'til current operation is finished");
                folderBrowserDialog.SelectedPath = (string)GRegistry.GetRegValue(key, "ex_dir", string.Empty);
                folderBrowserDialog.ShowNewFolderButton = true;
                folderBrowserDialog.Description = "Select Folder to Extract to.";
                if (folderBrowserDialog.ShowDialog() != DialogResult.OK) return;
                textBox1.Text = folderBrowserDialog.SelectedPath + Path.DirectorySeparatorChar;
                GRegistry.SetRegValue(key, "ex_dir", textBox1.Text, RegistryValueKind.String);

                if (GRegistry.GetRegValue(key, "initial_dir", null) == null)
                    GRegistry.SetRegValue(key, "initial_dir", textBox1.Text, RegistryValueKind.String);


            }
            catch (Exception ex)
            {
                MessageBox.Show(ex.Message);
            }

        }

        private void button6_Click(object sender, EventArgs e)
        {
            try
            {
                if (backgroundWorker.IsBusy)
                    throw new Exception("Wait 'til current operation is finished");
                openFileDialogIfr.InitialDirectory = (string)GRegistry.GetRegValue(key, "pack_dir", string.Empty);
                if (openFileDialogIfr.ShowDialog() != DialogResult.OK) return;
                if (string.IsNullOrEmpty(openFileDialogIfr.FileName)) return;
                label3.Text = openFileDialogIfr.FileName;
                SetBFPath();
            }
            catch (Exception ex)
            {
                MessageBox.Show(ex.Message);
            }
        }

        private void SetBFPath()
        {
            string s = label3.Text;
            if (string.IsNullOrEmpty(s))
            {
                label3.Text = "No file selected";
                return;
            }
            if (!label3.Text.ToLower().EndsWith("battle.fs"))
                label3.Text += "battle.fs";
            s = s.Replace(Path.AltDirectorySeparatorChar, Path.DirectorySeparatorChar);
            BattleFiles.BattlePath = s.Remove(s.LastIndexOf(Path.DirectorySeparatorChar));
            if (label3.Text.Length > 45)
            {
                string s1 = label3.Text.Remove(21);
                string s2 = label3.Text.Substring(label3.Text.Length - 21);
                label3.Text = s1 + "..." +s2;
            }
            if (!s.EndsWith("" + Path.DirectorySeparatorChar))
                s = s.Remove(s.LastIndexOf(Path.DirectorySeparatorChar) + 1);

            GRegistry.SetRegValue(key, "pack_dir", s, RegistryValueKind.String);
            listBox1.Items.Clear();
            listBox1.Items.AddRange(BattleFiles.FileNames);
            listBox1.ToString();
        }

        private void button2_Click(object sender, EventArgs e)
        {
            try
            {
                Work(0);
            }
            catch (Exception ex)
            {
                MessageBox.Show(ex.Message);
            }
        }

        private void Work(byte all)
        {
            if (backgroundWorker.IsBusy)
                throw new Exception("Wait 'til current operation is finished");
            this.type = all;
            ValidateT();

            progressBar.Value = 0;
            textBox1.Enabled = false;
            if (type == 1)
                progressBar.Maximum = max = listBox1.Items.Count;
            else if(type == 0)
            {
                progressBar.Maximum = max = listBox1.SelectedItems.Count;
                selection = new string[listBox1.SelectedItems.Count]; int i = 0;
                foreach (string s in listBox1.SelectedItems)
                    selection[i++] = s;
            }
            else if (type == 2)
            {
                progressBar.Maximum = max = 144;
                selection = new string[144]; int i = 0, sub = 0;
                foreach (string s in listBox1.Items)
                {
                    if (i > 143) break;
                    if (s.StartsWith("c0m") && s.Length == 10)
                    {
                        sub = Int32.Parse(s.Substring(3, 3));
                        if (sub < 144 && sub > -1)
                            selection[i++] = s;
                    }
                }
            }
            smax = "/" + max;
            ext = 0; timer1.Enabled = true; timer1.Start();
            backgroundWorker.RunWorkerAsync();

            GRegistry.SetRegValue(key, "ex_dir", textBox1.Text, RegistryValueKind.String);
        }

        private void FixTextBox(ref TextBox t)
        {
            string s = t.Text;
            if (string.IsNullOrEmpty(s))
                s = "" + Path.DirectorySeparatorChar;
            else if (s[s.Length - 1] != Path.DirectorySeparatorChar &&
                    s[s.Length - 1] != Path.AltDirectorySeparatorChar)
                    s += Path.DirectorySeparatorChar;
            t.Text = s;
        }

        private void ValidateT()
        {
            if (string.IsNullOrEmpty(textBox1.Text) || label3.Text == "No file selected")
            {
                throw new Exception("Select a folder to extract/pack from/to.");
            }
            FixTextBox(ref textBox1);
            dir = textBox1.Text;
        }

        private void backgroundWorker_DoWork(object sender, DoWorkEventArgs e)
        {
            if (type == 1)
            {
                ExtractAllInListBox(dir);
            }
            else if (type == 0 || type == 2)
            {
                foreach (string s in selection)
                {
                    ExtractFile(s, dir); ext++;
                }
            }
        }

        private void backgroundWorker_ProgressChanged(object sender, ProgressChangedEventArgs e)
        {
            progressBar.Value = ext;
            label1.Text = ext + smax;
        }

        private void backgroundWorker_RunWorkerCompleted(object sender, RunWorkerCompletedEventArgs e)
        {
            textBox1.Enabled = true;
            progressBar.Value = progressBar.Maximum;
            timer1.Stop(); timer1.Enabled = false;
            label1.Text = "Finished!";
        }

        private void timer1_Tick(object sender, EventArgs e)
        {
            //if (all)
            //    ext = BattleFiles.PackedFiles;
            backgroundWorker.ReportProgress(0);
        }        
    }
}
