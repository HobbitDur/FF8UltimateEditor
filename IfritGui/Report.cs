using System;
using System.Windows.Forms;
using Microsoft.Win32;

namespace Ifrit
{
    public partial class Report : Form
    {
        #region Variables

        RegistryKey regKey;
        Main main;

        #endregion

        #region Startup

        public Report(string enemyName, Main main)
        {
            if (regKey == null)
                regKey = Registry.CurrentUser.CreateSubKey(Ifrit.Main.REG_PATH, RegistryKeyPermissionCheck.ReadWriteSubTree);
            InitializeComponent();
            this.Text = enemyName + ": Stat points pr. lvl.";
            this.main = main;
        }
        private void Report_Load(object sender, EventArgs e)
        {
            Fill_DropDownList(cbAvaragePartyLevel);
            Fill_DropDownList(cbFinnishedCharLvl);

            if (regKey.GetValue("Grid_alevel") != null)
                cbAvaragePartyLevel.SelectedIndex = (int)regKey.GetValue("Grid_alevel");
            else
                cbAvaragePartyLevel.SelectedIndex = 1;

            if (regKey.GetValue("Grid_flevel") != null)
                cbFinnishedCharLvl.SelectedIndex = (int)regKey.GetValue("Grid_flevel");
            else
                cbFinnishedCharLvl.SelectedIndex = 1;


            if (regKey.GetValue("Grid_level") != null)
                nudLevelPrRow.Value = (int)regKey.GetValue("Grid_level");
            else
                nudLevelPrRow.Value = 1;

            main.Calc_GridView(gridView, (short)nudLevelPrRow.Value, (short)cbAvaragePartyLevel.SelectedIndex, (short)cbFinnishedCharLvl.SelectedIndex);

            int i;
            foreach (DataGridViewColumn col in gridView.Columns)
            {
                if (regKey.GetValue("Grid_" + col.Name + "_index") != null)
                {
                    
                    i = (int)regKey.GetValue("Grid_" + col.Name + "_index");
                    if (i < gridView.ColumnCount)
                        col.DisplayIndex = i;
                    else
                        col.DisplayIndex = col.DisplayIndex;
                }
                if (regKey.GetValue("Grid_" + col.Name + "_width") != null)
                {
                    col.Width = (int)regKey.GetValue("Grid_" + col.Name + "_width");
                }
            }

            main.ReOpenToolWindow(true);
        }
        private void Fill_DropDownList(ComboBox dpl)
        {
            for (int i = 1; i < 101; i++)
            {
                dpl.Items.Add(i);
            }
        }

        #endregion

        #region Events

        private void cbAvaragePartyLevel_SelectedIndexChanged(object sender, EventArgs e)
        {
            regKey.SetValue("Grid_alevel", cbAvaragePartyLevel.SelectedIndex, RegistryValueKind.DWord);
            main.Calc_GridView(gridView, (short)nudLevelPrRow.Value, (short)cbAvaragePartyLevel.SelectedIndex, (short)cbFinnishedCharLvl.SelectedIndex);
        }

        private void nudLevelPrRow_ValueChanged(object sender, EventArgs e)
        {
            regKey.SetValue("Grid_level", nudLevelPrRow.Value, RegistryValueKind.DWord);
            main.Calc_GridView(gridView, (short)nudLevelPrRow.Value, (short)cbAvaragePartyLevel.SelectedIndex, (short)cbFinnishedCharLvl.SelectedIndex);
        }

        private void cbFinnishedCharLvl_SelectedIndexChanged(object sender, EventArgs e)
        {
            regKey.SetValue("Grid_flevel", cbFinnishedCharLvl.SelectedIndex, RegistryValueKind.DWord);
            main.Calc_GridView(gridView, (short)nudLevelPrRow.Value, (short)cbAvaragePartyLevel.SelectedIndex, (short)cbFinnishedCharLvl.SelectedIndex);
        }

        private void gridView_ColumnDisplayIndexChanged(object sender, DataGridViewColumnEventArgs e)
        {
            regKey.SetValue("Grid_" + e.Column.Name + "_index", e.Column.DisplayIndex, RegistryValueKind.DWord);
        }

        private void gridView_ColumnWidthChanged(object sender, DataGridViewColumnEventArgs e)
        {
            regKey.SetValue("Grid_" + e.Column.Name + "_width", e.Column.Width, RegistryValueKind.DWord);
        }

        #endregion

        #region Get Methods

        public double Get_Avg_Level() { return Convert.ToDouble(cbAvaragePartyLevel.SelectedIndex); }
        public double Get_F_Level() { return Convert.ToDouble(cbFinnishedCharLvl.SelectedIndex); }
        public short Get_Level_Inc() { return Convert.ToInt16(nudLevelPrRow.Value); }
        public DataGridView Get_GridView() { return gridView; }

        #endregion

        #region Closeup

        private void btnClose_Click(object sender, EventArgs e)
        {
            this.Close(); this.Dispose();
        }
        private void Report_FormClosed(object sender, FormClosedEventArgs e)
        {
            main.ReOpenToolWindow(false);
        }

        #endregion
    }
}
