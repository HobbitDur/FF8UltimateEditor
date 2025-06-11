using System;
using System.Diagnostics;
using System.Windows.Forms;

namespace Ifrit
{
    public partial class About : Form
    {
        public About()
        {
            InitializeComponent();
            linkLabel1.Links[0].LinkData = "mailto:gjoerulv@hotmail.com";
            linkLabel2.Links[0].LinkData = "http://forums.qhimm.com/index.php?topic=8741.0";
        }

        private void linkLabel1_LinkClicked(object sender, LinkLabelLinkClickedEventArgs e)
        {
            try
            {
                string target = e.Link.LinkData as String;
                Process.Start(target);
            }
            catch (System.Exception ex)
            {
                MessageBox.Show(this, ex.Message);
            } 

        }

        private void btnClose_Click(object sender, EventArgs e)
        {
            this.Close();
        }
    }
}
