# Address Jigger PERFECT FOR PKC 
by [abu](https://discord.com/users/769155775163138048) (chatgpt)

Address Jigger is a desktop application for generating realistic address variants from CSV files.

It is designed to create subtle, moderate, or aggressive address transformations while keeping addresses readable and postal-looking.

## Features

- Bulk CSV processing
- Single-address preview mode
- Address jig generation
- City name jig generation
- Road-type variations
- OCR-style character substitutions
- Copy results to clipboard
- Export results to CSV
- Automatically opens exported CSV files
- Dark mode interface
- One-click EXE deployment via PyInstaller

## CSV Format

Input CSV should contain columns similar to:

```csv
Name,Address,Postcode,City
John Smith,12 Oak Road,WS1 1AA,Walsall
```

Supported column names include:

- Name
- Address
- Postcode
- City

## Transformation Strength

### 1 — Subtle
Applies 1–2 transformations.

### 2 — Moderate
Applies 2–4 transformations.

### 3 — Aggressive
Applies 4–6 transformations.

Examples:

```text
12 Oak Road
→ No. 12 Oak Rd

Walsall
→ VVaIsaII
```

## Running From Source

Requirements:

```bash
pip install PyQt5
```

Run:

```bash
python "abu's address jigger.py"
```

## Building EXE

Install PyInstaller:

```bash
pip install pyinstaller
```

Build:

```bash
pyinstaller --onefile --windowed --clean --noupx --name "Address Jigger" "abu's address jigger.py"
```

Output:

```text
dist/Address Jigger.exe
```

## Included Files

- abu's address jigger.py
- Test_Addresses.csv
- build_address_jigger.bat
- README.md

## License

For educational and internal use.
