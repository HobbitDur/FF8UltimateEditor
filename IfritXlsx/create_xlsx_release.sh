./.venv/Scripts/pyinstaller.exe -n ifrit-xlsx -F --specpath release/build --distpath release --workpath release/build --paths venv/Lib/site-packages main.py;
cp -r Resources/ release/;
rm -rf OriginalFiles/decompressed_battle ;
mkdir -p release/OriginalFiles/;
cp OriginalFiles/en_battle/battle.* release/OriginalFiles;
rm -r release/build