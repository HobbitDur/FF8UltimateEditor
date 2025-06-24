from collections import defaultdict
from itertools import combinations

# Load the encounter data from the file
def parse_encounters(file_path):
    encounters = {}
    with open(file_path, 'r') as f:
        lines = f.readlines()
    
    current_id = None
    buffer = []
    
    for line in lines:
        line = line.strip()
        if line.startswith("Encounter ID"):
            if current_id is not None:
                encounters[current_id] = buffer
                buffer = []
            current_id = int(line.split()[2][:-1])
        elif line:
            values = tuple(map(int, line.split(',')))
            buffer.append(values)
    
    # Add last encounter
    if current_id is not None and buffer:
        encounters[current_id] = buffer
    
    return encounters

def group_by_full_match(encounters):
    from collections import defaultdict

    line_groups = {4: defaultdict(list), 3: defaultdict(list), 2: defaultdict(list), 1: defaultdict(list)}
    unmatched = set(encounters.keys())

    for enc_id, lines in encounters.items():
        # Try combinations of 4 down to 1 lines
        for count in range(4, 0, -1):
            matched = False
            for indices in combinations(range(4), count):
                key = tuple(lines[i] for i in indices)
                key_index = tuple(indices)
                line_groups[count][(key_index, key)].append(enc_id)
            # No early break: we allow a scene to be in all smaller groups too

    final_groups = {1: [], 2: [], 3: [], 4: []}
    seen_ids = set()

    for count in range(4, 0, -1):
        for (line_nums, values), ids in line_groups[count].items():
            ids_set = set(ids)
            if len(ids_set - seen_ids) >= 2:
                group_ids = sorted(ids_set - seen_ids)
                final_groups[count].append((group_ids, list(line_nums), [values[i] for i in range(len(values))]))
                seen_ids.update(group_ids)

    unmatched = unmatched - seen_ids
    return final_groups, sorted(unmatched)

# Group by identical line content
def group_shared_lines(encounters):
    shared_lines = defaultdict(lambda: defaultdict(list))  # {line_number: {line_values: [encounter_ids]}}
    
    for enc_id, lines in encounters.items():
        for i, line in enumerate(lines):  # i is 0 to 3
            shared_lines[i][line].append(enc_id)
    
    return shared_lines

file_path = 'output.txt'  # change this to your filename
encounters = parse_encounters(file_path)
grouped, unmatched = group_by_full_match(encounters)

def format_id_ranges(id_list):
    """Convert a sorted list of integers into range strings like '1-5, 9-11, 13'."""
    if not id_list:
        return ""
    ranges = []
    start = prev = id_list[0]
    for n in id_list[1:]:
        if n == prev + 1:
            prev = n
        else:
            ranges.append(f"{start}-{prev}" if start != prev else f"{start}")
            start = prev = n
    ranges.append(f"{start}-{prev}" if start != prev else f"{start}")
    return ", ".join(ranges)

# Output from 4 matches down to 1
for count in range(4, 0, -1):
    print(f"\n=== Encounters sharing {count} unknown(s) ===")
    for ids, line_nums, values in grouped[count]:
        print(f"Encounter IDs: {format_id_ranges(ids)} - Shared Unknowns: {line_nums} - Values: {list(values)}")

# List completely unmatched encounters
print("\n=== Encounters with no matching unknowns ===")
print(sorted(unmatched))