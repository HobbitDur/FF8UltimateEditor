using System;
using System.ComponentModel;
using System.Drawing;
using System.Runtime.InteropServices;
using System.Windows.Forms;
using Ifrit.Code;

namespace Ifrit
{
    public partial class Pack : Form
    {

        const int MF_BYPOSITION = 0x400;
        Timer timer = new Timer();
        BackgroundWorker bw = new BackgroundWorker();
        ProgressBar bar = new ProgressBar();
        int packed, max = 0; string d, s; Label lbl2; bool error = false;

        public Pack(string sourceDir, string destDir)
        {
            InitializeComponent(); this.Height = 12 + bar.Height * 5;
            bar.Location = new Point(8, (this.Height / 3 - (bar.Height / 2)) - 4);
            d = destDir; s = sourceDir;

            Label lbl1 = new Label(); lbl1.Location = new Point(8, bar.Location.Y + bar.Height + 4);
            lbl1.Text = "Files packed: "; lbl1.Width = 8 + (int)lbl1.Font.Size * (lbl1.Text.Length + 1);

            lbl2 = new Label(); lbl2.Location = new Point(lbl1.Width + 8, lbl1.Location.Y); lbl2.Text = "";
            lbl2.Width = 8 + (int)lbl2.Font.Size * 18;

            this.Width = 24 + lbl1.Width + lbl2.Width + ((8 * (int)this.Font.Size) + 16);
            bar.Width = this.Width - 32;

            try
            {
                BattleFileHandler h = new BattleFileHandler(destDir);

                max = h.FileNames.Length;
            }
            catch (Exception ex)
            {
                #if DEBUG
                Console.WriteLine(ex.Message);
                #endif
            }
            if(max < 1)
                max = BattleFileHandler.NrOfDefaultFiles(s);

            bar.Maximum = max;

            this.Controls.AddRange(new Control[] { lbl1, lbl2, bar });

            IntPtr hMenu = GetSystemMenu(this.Handle, false);
            int menuItemCount = GetMenuItemCount(hMenu);
            RemoveMenu(hMenu, menuItemCount - 1, MF_BYPOSITION);

            bw.WorkerReportsProgress = true;
            bw.WorkerSupportsCancellation = true;
            bw.DoWork += new DoWorkEventHandler(BWDo);
            bw.ProgressChanged += new ProgressChangedEventHandler(BWPro);
            bw.RunWorkerCompleted += new RunWorkerCompletedEventHandler(BWDone);

            timer.Interval = 100;
            timer.Tick += new EventHandler(TimerTick);

            timer.Enabled = true;
            timer.Start();

            bw.RunWorkerAsync();
            
        }


        private void TimerTick(object sender, EventArgs e)
        {
            try
            {
                bw.ReportProgress(0);
            }
            catch (Exception ex)
            {
                timer.Stop();
                timer.Enabled = false;
                MessageBox.Show(ex.Message);
                error = true;
                bw.CancelAsync();
                BWDone(null, null);
            }
        }

        private void PackIt()
        {
            packed = 0;
            BattleFileHandler.PackBattleFiles(s, d, ref packed);
        }

        private void BWDo(object sender, DoWorkEventArgs e)
        {
            try
            {
                PackIt();
            }
            catch (Exception ex)
            {
                MessageBox.Show(ex.Message);
                error = true;
            }
        }

        private void BWPro(object sender, ProgressChangedEventArgs e)
        {
            bar.Value = packed;
            lbl2.Text = packed + "/" + max;
        }

        private void BWDone(object sender, RunWorkerCompletedEventArgs e)
        {
            try
            {
                lbl2.Text = "DONE!";
                if (error) lbl2.Text = "An error ocurred.";
                timer.Stop();
                timer.Enabled = false;
                Button btn = new Button();
                btn.Text = "Close";
                btn.Location = new Point(lbl2.Location.X + lbl2.Width + 8, lbl2.Location.Y);
                btn.Width = (btn.Text.Length * (int)btn.Font.Size) + 16;
                btn.Click += new EventHandler(btn_Click);
                this.Controls.Add(btn);
            }
            catch (Exception ex)
            {
                MessageBox.Show(ex.Message);
                this.Close();
            }
        }

        void btn_Click(object sender, EventArgs e)
        {
            this.Close();
        }

        [DllImport("User32")]
        private static extern int RemoveMenu(IntPtr hMenu, int nPosition, int wFlags);
        [DllImport("User32")]
        private static extern IntPtr GetSystemMenu(IntPtr hWnd, bool bRevert);
        [DllImport("User32")]
        private static extern int GetMenuItemCount(IntPtr hWnd);
    }
}