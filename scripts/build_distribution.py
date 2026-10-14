"""Export current source; user installations are distributed as release EXEs."""
import argparse
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from scripts.export_next_source import export, source_files

def build(output,source=ROOT):
    return export(output,source)

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    print(build(parser.parse_args().output))
