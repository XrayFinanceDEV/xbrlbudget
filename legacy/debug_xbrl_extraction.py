"""
Debug script to check what the XBRL parser is extracting
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from lxml import etree
from decimal import Decimal
from importers.xbrl_parser_enhanced import EnhancedXBRLParser
from datetime import datetime

# Find the XBRL file
import glob
xbrl_files = glob.glob("*.xbrl") + glob.glob("**/*.xbrl", recursive=True)
if not xbrl_files:
    print("No XBRL files found!")
    sys.exit(1)

xbrl_file = xbrl_files[0]
print(f"Analyzing: {xbrl_file}\n")

# Create parser
parser = EnhancedXBRLParser()

# Parse file
root = parser.parse_file(xbrl_file)
contexts = parser.extract_contexts(root)

print(f"=== CONTEXTS FOUND: {len(contexts)} ===")
instant_contexts = [c for c in contexts.values() if c['period_type'] == 'instant']
duration_contexts = [c for c in contexts.values() if c['period_type'] == 'duration']
print(f"Instant contexts: {len(instant_contexts)}")
print(f"Duration contexts: {len(duration_contexts)}")

# Show contexts by year
years_instant = {}
years_duration = {}
for ctx in contexts.values():
    year = ctx.get('year')
    if year:
        if ctx['period_type'] == 'instant':
            years_instant[year] = years_instant.get(year, 0) + 1
        else:
            years_duration[year] = years_duration.get(year, 0) + 1

print(f"\nInstant contexts by year: {years_instant}")
print(f"Duration contexts by year: {years_duration}")

# Extract facts
facts_by_year = parser.extract_facts(root, contexts)

print(f"\n=== FACTS EXTRACTED ===")
for year in sorted(facts_by_year.keys()):
    year_facts = facts_by_year[year]
    instant_facts = year_facts.get('instant', {})
    duration_facts = year_facts.get('duration', {})

    print(f"\nYear {year}:")
    print(f"  Instant facts: {len(instant_facts)}")
    print(f"  Duration facts: {len(duration_facts)}")

    # Check for specific income statement tags in duration
    income_tags_found = []
    income_tags_to_check = [
        'VariazioniRimanenze',
        'IncrImmobPerLavoriInterni',
        'CostiPersonale',
        'VariazioniRimanenzeMatPrime',
        'InteressiOneriFinanziari',
        'AltriProventiFinanziari',
        'UtiliPerditeCambi',
        'Imposte'
    ]

    for tag in duration_facts.keys():
        local_name = etree.QName(tag).localname if tag.startswith('{') else tag.split(':')[-1]
        for check_tag in income_tags_to_check:
            if check_tag in local_name:
                income_tags_found.append((local_name, duration_facts[tag]))
                break

    if income_tags_found:
        print(f"\n  Income statement tags in duration facts:")
        for tag_name, value in income_tags_found:
            print(f"    {tag_name}: {value}")
    else:
        print(f"\n  WARNING: No income statement tags found in duration facts!")
        print(f"\n  Sample duration fact tags (first 10):")
        for i, tag in enumerate(list(duration_facts.keys())[:10]):
            local_name = etree.QName(tag).localname if tag.startswith('{') else tag.split(':')[-1]
            print(f"    {local_name}: {duration_facts[tag]}")

print("\n=== DONE ===")
