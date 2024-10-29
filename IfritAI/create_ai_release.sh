./.venv/Scripts/pyinstaller.exe -n ifrit-ai -F --specpath release/build --distpath release --workpath release/build --paths venv/Lib/site-packages --onefile --noconsole --icon=../../Resources/icon.ico main.py;
mkdir -p release/OriginalFiles/;
cp -r Resources/ release/;
cp -r OriginalFiles/ release/;
rm -r release/build