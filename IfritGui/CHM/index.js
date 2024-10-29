<SCRIPT language="JavaScript">
<!--
//==========================================================================//
//	Function:	searchSelectBox(in_sFormName, in_sInputName, in_sSelectName)
//	Purpose: Acts as a "searchable" input for a given select box.
//	Parameters:
//		in_sFormName 	- The form name where the elements live
//		in_sInputName 	- The "search input element name.
//		in_sSelectName	- The select box to search against.
//
//==========================================================================//
function searchSelectBox(in_sFormName, in_sInputName, in_sSelectName)
{
	sSearchString = document.forms[in_sFormName].elements[in_sInputName].value.toUpperCase();
	iSearchTextLength = sSearchString.length;

	for (j=0; j < document.forms[in_sFormName].elements[in_sSelectName].options.length; j++)
	{
		sOptionText = document.forms[in_sFormName].elements[in_sSelectName].options[j].text;
		sOptionComp = sOptionText.substr(0, iSearchTextLength).toUpperCase();

		if(sSearchString == sOptionComp)
		{
			document.forms[in_sFormName].elements[in_sSelectName].selectedIndex = j;
			break;
		}
	}
}
//-->

<!--
function goSelect(cbSearchSelect) {
with(cbSearchSelect) {
parent.frames['rechts'].location=options[selectedIndex].value; // jump to that option's value
}
}
//-->