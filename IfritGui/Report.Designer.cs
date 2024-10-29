namespace Ifrit
{
    partial class Report
    {
        /// <summary>
        /// Required designer variable.
        /// </summary>
        private System.ComponentModel.IContainer components = null;

        /// <summary>
        /// Clean up any resources being used.
        /// </summary>
        /// <param name="disposing">true if managed resources should be disposed; otherwise, false.</param>
        protected override void Dispose(bool disposing)
        {
            if (disposing && (components != null))
            {
                components.Dispose();
            }
            base.Dispose(disposing);
        }

        #region Windows Form Designer generated code

        /// <summary>
        /// Required method for Designer support - do not modify
        /// the contents of this method with the code editor.
        /// </summary>
        private void InitializeComponent()
        {
            this.gridView = new System.Windows.Forms.DataGridView();
            this.cbAvaragePartyLevel = new System.Windows.Forms.ComboBox();
            this.nudLevelPrRow = new System.Windows.Forms.NumericUpDown();
            this.lblFinishedCharLvl = new System.Windows.Forms.Label();
            this.cbFinnishedCharLvl = new System.Windows.Forms.ComboBox();
            this.label1 = new System.Windows.Forms.Label();
            this.lblAverageLvl = new System.Windows.Forms.Label();
            this.btnClose = new System.Windows.Forms.Button();
            this.panelTop = new System.Windows.Forms.Panel();
            this.panelMid = new System.Windows.Forms.Panel();
            this.CNetHelpProvider = new System.Windows.Forms.HelpProvider();
            this.ColumnHP = new System.Windows.Forms.DataGridViewTextBoxColumn();
            this.ColumnSTR = new System.Windows.Forms.DataGridViewTextBoxColumn();
            this.ColumnMAG = new System.Windows.Forms.DataGridViewTextBoxColumn();
            this.ColumnVIT = new System.Windows.Forms.DataGridViewTextBoxColumn();
            this.ColumnSPR = new System.Windows.Forms.DataGridViewTextBoxColumn();
            this.ColumnSPD = new System.Windows.Forms.DataGridViewTextBoxColumn();
            this.ColumnEVA = new System.Windows.Forms.DataGridViewTextBoxColumn();
            this.ColumnEXP = new System.Windows.Forms.DataGridViewTextBoxColumn();
            this.ColumnExtraEXP = new System.Windows.Forms.DataGridViewTextBoxColumn();
            ((System.ComponentModel.ISupportInitialize)(this.gridView)).BeginInit();
            ((System.ComponentModel.ISupportInitialize)(this.nudLevelPrRow)).BeginInit();
            this.panelTop.SuspendLayout();
            this.panelMid.SuspendLayout();
            this.SuspendLayout();
            // 
            // gridView
            // 
            this.gridView.AllowUserToAddRows = false;
            this.gridView.AllowUserToDeleteRows = false;
            this.gridView.AllowUserToOrderColumns = true;
            this.gridView.AllowUserToResizeRows = false;
            this.gridView.ColumnHeadersHeightSizeMode = System.Windows.Forms.DataGridViewColumnHeadersHeightSizeMode.AutoSize;
            this.gridView.Columns.AddRange(new System.Windows.Forms.DataGridViewColumn[] {
            this.ColumnHP,
            this.ColumnSTR,
            this.ColumnMAG,
            this.ColumnVIT,
            this.ColumnSPR,
            this.ColumnSPD,
            this.ColumnEVA,
            this.ColumnEXP,
            this.ColumnExtraEXP});
            this.gridView.Dock = System.Windows.Forms.DockStyle.Top;
            this.CNetHelpProvider.SetHelpKeyword(this.gridView, "FFVIII simple enemy editor_Form_Report.htm#Report_gridView");
            this.CNetHelpProvider.SetHelpNavigator(this.gridView, System.Windows.Forms.HelpNavigator.Topic);
            this.gridView.Location = new System.Drawing.Point(0, 0);
            this.gridView.Name = "gridView";
            this.gridView.ReadOnly = true;
            this.gridView.RowHeadersWidth = 90;
            this.gridView.RowHeadersWidthSizeMode = System.Windows.Forms.DataGridViewRowHeadersWidthSizeMode.DisableResizing;
            this.gridView.SelectionMode = System.Windows.Forms.DataGridViewSelectionMode.FullRowSelect;
            this.CNetHelpProvider.SetShowHelp(this.gridView, true);
            this.gridView.Size = new System.Drawing.Size(912, 346);
            this.gridView.TabIndex = 4;
            this.gridView.ColumnDisplayIndexChanged += new System.Windows.Forms.DataGridViewColumnEventHandler(this.gridView_ColumnDisplayIndexChanged);
            this.gridView.ColumnWidthChanged += new System.Windows.Forms.DataGridViewColumnEventHandler(this.gridView_ColumnWidthChanged);
            // 
            // cbAvaragePartyLevel
            // 
            this.cbAvaragePartyLevel.DropDownStyle = System.Windows.Forms.ComboBoxStyle.DropDownList;
            this.cbAvaragePartyLevel.FormattingEnabled = true;
            this.CNetHelpProvider.SetHelpKeyword(this.cbAvaragePartyLevel, "FFVIII simple enemy editor_Form_Report.htm#Report_cbAvaragePartyLevel");
            this.CNetHelpProvider.SetHelpNavigator(this.cbAvaragePartyLevel, System.Windows.Forms.HelpNavigator.Topic);
            this.cbAvaragePartyLevel.Location = new System.Drawing.Point(148, 3);
            this.cbAvaragePartyLevel.Name = "cbAvaragePartyLevel";
            this.CNetHelpProvider.SetShowHelp(this.cbAvaragePartyLevel, true);
            this.cbAvaragePartyLevel.Size = new System.Drawing.Size(77, 25);
            this.cbAvaragePartyLevel.TabIndex = 1;
            this.cbAvaragePartyLevel.SelectedIndexChanged += new System.EventHandler(this.cbAvaragePartyLevel_SelectedIndexChanged);
            // 
            // nudLevelPrRow
            // 
            this.CNetHelpProvider.SetHelpKeyword(this.nudLevelPrRow, "FFVIII simple enemy editor_Form_Report.htm#Report_nudLevelPrRow");
            this.CNetHelpProvider.SetHelpNavigator(this.nudLevelPrRow, System.Windows.Forms.HelpNavigator.Topic);
            this.nudLevelPrRow.Location = new System.Drawing.Point(629, 5);
            this.nudLevelPrRow.Minimum = new decimal(new int[] {
            1,
            0,
            0,
            0});
            this.nudLevelPrRow.Name = "nudLevelPrRow";
            this.CNetHelpProvider.SetShowHelp(this.nudLevelPrRow, true);
            this.nudLevelPrRow.Size = new System.Drawing.Size(61, 23);
            this.nudLevelPrRow.TabIndex = 3;
            this.nudLevelPrRow.Value = new decimal(new int[] {
            1,
            0,
            0,
            0});
            this.nudLevelPrRow.ValueChanged += new System.EventHandler(this.nudLevelPrRow_ValueChanged);
            // 
            // lblFinishedCharLvl
            // 
            this.lblFinishedCharLvl.AutoSize = true;
            this.CNetHelpProvider.SetHelpKeyword(this.lblFinishedCharLvl, "FFVIII simple enemy editor_Form_Report.htm#Report_lblFinishedCharLvl");
            this.CNetHelpProvider.SetHelpNavigator(this.lblFinishedCharLvl, System.Windows.Forms.HelpNavigator.Topic);
            this.lblFinishedCharLvl.Location = new System.Drawing.Point(257, 6);
            this.lblFinishedCharLvl.Name = "lblFinishedCharLvl";
            this.CNetHelpProvider.SetShowHelp(this.lblFinishedCharLvl, true);
            this.lblFinishedCharLvl.Size = new System.Drawing.Size(129, 17);
            this.lblFinishedCharLvl.TabIndex = 78;
            this.lblFinishedCharLvl.Text = "Finished char. level";
            // 
            // cbFinnishedCharLvl
            // 
            this.cbFinnishedCharLvl.DropDownStyle = System.Windows.Forms.ComboBoxStyle.DropDownList;
            this.cbFinnishedCharLvl.FormattingEnabled = true;
            this.CNetHelpProvider.SetHelpKeyword(this.cbFinnishedCharLvl, "FFVIII simple enemy editor_Form_Report.htm#Report_cbFinnishedCharLvl");
            this.CNetHelpProvider.SetHelpNavigator(this.cbFinnishedCharLvl, System.Windows.Forms.HelpNavigator.Topic);
            this.cbFinnishedCharLvl.Location = new System.Drawing.Point(392, 3);
            this.cbFinnishedCharLvl.Name = "cbFinnishedCharLvl";
            this.CNetHelpProvider.SetShowHelp(this.cbFinnishedCharLvl, true);
            this.cbFinnishedCharLvl.Size = new System.Drawing.Size(77, 25);
            this.cbFinnishedCharLvl.TabIndex = 2;
            this.cbFinnishedCharLvl.SelectedIndexChanged += new System.EventHandler(this.cbFinnishedCharLvl_SelectedIndexChanged);
            // 
            // label1
            // 
            this.label1.AutoSize = true;
            this.CNetHelpProvider.SetHelpKeyword(this.label1, "FFVIII simple enemy editor_Form_Report.htm#Report_label1");
            this.CNetHelpProvider.SetHelpNavigator(this.label1, System.Windows.Forms.HelpNavigator.Topic);
            this.label1.Location = new System.Drawing.Point(514, 6);
            this.label1.Name = "label1";
            this.CNetHelpProvider.SetShowHelp(this.label1, true);
            this.label1.Size = new System.Drawing.Size(109, 17);
            this.label1.TabIndex = 76;
            this.label1.Text = "Level increment";
            // 
            // lblAverageLvl
            // 
            this.lblAverageLvl.AutoSize = true;
            this.CNetHelpProvider.SetHelpKeyword(this.lblAverageLvl, "FFVIII simple enemy editor_Form_Report.htm#Report_lblAverageLvl");
            this.CNetHelpProvider.SetHelpNavigator(this.lblAverageLvl, System.Windows.Forms.HelpNavigator.Topic);
            this.lblAverageLvl.Location = new System.Drawing.Point(12, 6);
            this.lblAverageLvl.Name = "lblAverageLvl";
            this.CNetHelpProvider.SetShowHelp(this.lblAverageLvl, true);
            this.lblAverageLvl.Size = new System.Drawing.Size(130, 17);
            this.lblAverageLvl.TabIndex = 75;
            this.lblAverageLvl.Text = "Average party level";
            // 
            // btnClose
            // 
            this.btnClose.BackColor = System.Drawing.Color.FromArgb(((int)(((byte)(224)))), ((int)(((byte)(224)))), ((int)(((byte)(224)))));
            this.btnClose.DialogResult = System.Windows.Forms.DialogResult.Cancel;
            this.btnClose.Dock = System.Windows.Forms.DockStyle.Right;
            this.btnClose.FlatStyle = System.Windows.Forms.FlatStyle.System;
            this.btnClose.Font = new System.Drawing.Font("Georgia", 8F, System.Drawing.FontStyle.Bold);
            this.btnClose.ForeColor = System.Drawing.Color.Black;
            this.CNetHelpProvider.SetHelpKeyword(this.btnClose, "FFVIII simple enemy editor_Form_Report.htm#Report_btnClose");
            this.CNetHelpProvider.SetHelpNavigator(this.btnClose, System.Windows.Forms.HelpNavigator.Topic);
            this.btnClose.Location = new System.Drawing.Point(797, 346);
            this.btnClose.Name = "btnClose";
            this.CNetHelpProvider.SetShowHelp(this.btnClose, true);
            this.btnClose.Size = new System.Drawing.Size(115, 36);
            this.btnClose.TabIndex = 4;
            this.btnClose.Text = "Close";
            this.btnClose.UseVisualStyleBackColor = false;
            this.btnClose.Click += new System.EventHandler(this.btnClose_Click);
            // 
            // panelTop
            // 
            this.panelTop.Controls.Add(this.lblFinishedCharLvl);
            this.panelTop.Controls.Add(this.cbFinnishedCharLvl);
            this.panelTop.Controls.Add(this.label1);
            this.panelTop.Controls.Add(this.lblAverageLvl);
            this.panelTop.Controls.Add(this.cbAvaragePartyLevel);
            this.panelTop.Controls.Add(this.nudLevelPrRow);
            this.panelTop.Dock = System.Windows.Forms.DockStyle.Top;
            this.CNetHelpProvider.SetHelpKeyword(this.panelTop, "FFVIII simple enemy editor_Form_Report.htm#Report_panelTop");
            this.CNetHelpProvider.SetHelpNavigator(this.panelTop, System.Windows.Forms.HelpNavigator.Topic);
            this.panelTop.Location = new System.Drawing.Point(0, 0);
            this.panelTop.Name = "panelTop";
            this.CNetHelpProvider.SetShowHelp(this.panelTop, true);
            this.panelTop.Size = new System.Drawing.Size(912, 26);
            this.panelTop.TabIndex = 77;
            // 
            // panelMid
            // 
            this.panelMid.Controls.Add(this.btnClose);
            this.panelMid.Controls.Add(this.gridView);
            this.panelMid.Dock = System.Windows.Forms.DockStyle.Bottom;
            this.CNetHelpProvider.SetHelpKeyword(this.panelMid, "FFVIII simple enemy editor_Form_Report.htm#Report_panelMid");
            this.CNetHelpProvider.SetHelpNavigator(this.panelMid, System.Windows.Forms.HelpNavigator.Topic);
            this.panelMid.Location = new System.Drawing.Point(0, 30);
            this.panelMid.Name = "panelMid";
            this.CNetHelpProvider.SetShowHelp(this.panelMid, true);
            this.panelMid.Size = new System.Drawing.Size(912, 382);
            this.panelMid.TabIndex = 75;
            // 
            // CNetHelpProvider
            // 
            this.CNetHelpProvider.HelpNamespace = "FFVIII simple enemy editor.chm";
            // 
            // ColumnHP
            // 
            this.ColumnHP.HeaderText = "HP";
            this.ColumnHP.Name = "ColumnHP";
            this.ColumnHP.ReadOnly = true;
            // 
            // ColumnSTR
            // 
            this.ColumnSTR.HeaderText = "STR";
            this.ColumnSTR.Name = "ColumnSTR";
            this.ColumnSTR.ReadOnly = true;
            this.ColumnSTR.Width = 80;
            // 
            // ColumnMAG
            // 
            this.ColumnMAG.HeaderText = "MAG";
            this.ColumnMAG.Name = "ColumnMAG";
            this.ColumnMAG.ReadOnly = true;
            this.ColumnMAG.Width = 80;
            // 
            // ColumnVIT
            // 
            this.ColumnVIT.HeaderText = "VIT";
            this.ColumnVIT.Name = "ColumnVIT";
            this.ColumnVIT.ReadOnly = true;
            this.ColumnVIT.Width = 80;
            // 
            // ColumnSPR
            // 
            this.ColumnSPR.HeaderText = "SPR";
            this.ColumnSPR.Name = "ColumnSPR";
            this.ColumnSPR.ReadOnly = true;
            this.ColumnSPR.Width = 80;
            // 
            // ColumnSPD
            // 
            this.ColumnSPD.HeaderText = "SPD";
            this.ColumnSPD.Name = "ColumnSPD";
            this.ColumnSPD.ReadOnly = true;
            this.ColumnSPD.Width = 80;
            // 
            // ColumnEVA
            // 
            this.ColumnEVA.HeaderText = "EVA";
            this.ColumnEVA.Name = "ColumnEVA";
            this.ColumnEVA.ReadOnly = true;
            this.ColumnEVA.Width = 80;
            // 
            // ColumnEXP
            // 
            this.ColumnEXP.HeaderText = "EXP";
            this.ColumnEXP.Name = "ColumnEXP";
            this.ColumnEXP.ReadOnly = true;
            // 
            // ColumnExtraEXP
            // 
            this.ColumnExtraEXP.HeaderText = "Extra EXP";
            this.ColumnExtraEXP.Name = "ColumnExtraEXP";
            this.ColumnExtraEXP.ReadOnly = true;
            // 
            // Report
            // 
            this.AutoScaleDimensions = new System.Drawing.SizeF(8F, 17F);
            this.AutoScaleMode = System.Windows.Forms.AutoScaleMode.Font;
            this.ClientSize = new System.Drawing.Size(912, 412);
            this.Controls.Add(this.panelTop);
            this.Controls.Add(this.panelMid);
            this.Font = new System.Drawing.Font("Georgia", 8.25F);
            this.FormBorderStyle = System.Windows.Forms.FormBorderStyle.FixedSingle;
            this.CNetHelpProvider.SetHelpKeyword(this, "FFVIII simple enemy editor_Form_Report.htm");
            this.CNetHelpProvider.SetHelpNavigator(this, System.Windows.Forms.HelpNavigator.Topic);
            this.MaximizeBox = false;
            this.MinimizeBox = false;
            this.Name = "Report";
            this.CNetHelpProvider.SetShowHelp(this, true);
            this.ShowIcon = false;
            this.ShowInTaskbar = false;
            this.SizeGripStyle = System.Windows.Forms.SizeGripStyle.Hide;
            this.Text = "Report";
            this.FormClosed += new System.Windows.Forms.FormClosedEventHandler(this.Report_FormClosed);
            this.Load += new System.EventHandler(this.Report_Load);
            ((System.ComponentModel.ISupportInitialize)(this.gridView)).EndInit();
            ((System.ComponentModel.ISupportInitialize)(this.nudLevelPrRow)).EndInit();
            this.panelTop.ResumeLayout(false);
            this.panelTop.PerformLayout();
            this.panelMid.ResumeLayout(false);
            this.ResumeLayout(false);

        }

        #endregion

        private System.Windows.Forms.DataGridView gridView;
        private System.Windows.Forms.ComboBox cbAvaragePartyLevel;
        private System.Windows.Forms.NumericUpDown nudLevelPrRow;
        private System.Windows.Forms.Label lblAverageLvl;
        private System.Windows.Forms.Label label1;
        private System.Windows.Forms.Label lblFinishedCharLvl;
        private System.Windows.Forms.ComboBox cbFinnishedCharLvl;
        private System.Windows.Forms.Button btnClose;
        private System.Windows.Forms.Panel panelTop;
        private System.Windows.Forms.Panel panelMid;
        private System.Windows.Forms.HelpProvider CNetHelpProvider;
        private System.Windows.Forms.DataGridViewTextBoxColumn ColumnHP;
        private System.Windows.Forms.DataGridViewTextBoxColumn ColumnSTR;
        private System.Windows.Forms.DataGridViewTextBoxColumn ColumnMAG;
        private System.Windows.Forms.DataGridViewTextBoxColumn ColumnVIT;
        private System.Windows.Forms.DataGridViewTextBoxColumn ColumnSPR;
        private System.Windows.Forms.DataGridViewTextBoxColumn ColumnSPD;
        private System.Windows.Forms.DataGridViewTextBoxColumn ColumnEVA;
        private System.Windows.Forms.DataGridViewTextBoxColumn ColumnEXP;
        private System.Windows.Forms.DataGridViewTextBoxColumn ColumnExtraEXP;
    }
}