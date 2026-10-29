"""Automatic, readable bone names guessed from a model's rest pose (used to build bone_names.json).

FF8 bones have no name. This guesses one from the skeleton and where its parts sit in the rest pose
(animation 0, frame 0), in the viewer's space: +Y is up, the model faces -Z, so its right is +X.

The skeleton is cut into chains: a chain starts under the root or under a bone with several children,
and runs down while each bone has a single child. Each chain is named, then numbered from the body
outwards ("L arm 1", "L arm 2", ...; a one-bone chain gets no number):
- under the root, a centred chain is the body ("Body", or "Upper body"/"Lower body" when there are two);
- a chain that goes clearly to one side is a limb: a "leg" when it reaches the ground, an "arm"
  otherwise. Two mirrored limbs (same parent, same shape) the rest pose does not split on two sides
  take the file's order: left first, as in every vanilla skeleton; several of a kind on one side get a letter ("L leg A", "L leg B"), front to back for
  legs, top to bottom for arms;
- the head is found first (a head leaning in a fighting stance is off-centre): the heaviest bone (most
  vertices) attached on the body that sits above where its chain starts; "Neck" bones lead to it,
  "Head tip" bones (hair, ears...) follow it;
- of the other centred chains, one going backwards is a "Tail", the rest "Centre A", "Centre B"...;
- a chain branching off a limb or the head keeps that name plus a letter ("L arm > A1").
These are guesses: right on most humanoids, rough on unusual monsters, and meant to be curated.
"""

ROOT_NAME = "Root"

# Fractions of the model height
SIDE_THRESHOLD = 0.02      # a chain is on one side once its first half goes this far from its start in X
GROUND_REACH = 0.15        # a limb reaching this close to the lowest point of the model is a leg
TAIL_THRESHOLD = 0.05      # a centred chain going this far backwards (+Z) is a tail


def _letters(index: int) -> str:
    text = ""
    index += 1
    while index:
        index, rest = divmod(index - 1, 26)
        text = chr(ord("A") + rest) + text
    return text


def _mean(points):
    n = len(points)
    return tuple(sum(p[i] for p in points) / n for i in range(3))


def auto_bone_names(parents, joints, vertices_by_bone, lengths=None):
    """Names for every bone.

    parents: parent id of each bone, -1 (or 0xFFFF) for the root.
    joints: (x, y, z) origin of each bone in the rest pose.
    vertices_by_bone: per bone, the list of its (x, y, z) vertices in the rest pose.
    lengths: length of each bone (the file's bone size), used to recognise mirrored limbs.
    """
    nb = len(parents)
    parents = [-1 if p in (-1, 0xFFFF) or not (0 <= p < nb) else p for p in parents]
    names = [None] * nb
    children = [[] for _ in range(nb)]
    for bone, parent in enumerate(parents):
        if parent >= 0:
            children[parent].append(bone)

    all_points = [v for vs in vertices_by_bone for v in vs] or list(joints)
    if not all_points:
        return [f"Bone {k}" for k in range(nb)]
    min_y = min(p[1] for p in all_points)
    height = (max(p[1] for p in all_points) - min_y) or 1.0

    def subtree(bone):
        stack, out = [bone], []
        while stack:
            b = stack.pop()
            out.append(b)
            stack.extend(children[b])
        return out

    def subtree_points(bone):
        bones = subtree(bone)
        points = [v for b in bones for v in vertices_by_bone[b]]
        return points or [joints[b] for b in bones]

    # Cut the skeleton into chains
    chains = []            # list of bone lists
    chain_of = {}          # bone -> index of its chain
    for bone in range(nb):
        parent = parents[bone]
        if parent < 0:
            continue
        if parents[parent] >= 0 and len(children[parent]) == 1:
            continue       # continues its parent's chain
        chain = [bone]
        while len(children[chain[-1]]) == 1:
            chain.append(children[chain[-1]][0])
        for b in chain:
            chain_of[b] = len(chains)
        chains.append(chain)

    def attach_point(chain):
        # A bone's joint is where it starts, i.e. the end of its parent
        return joints[chain[0]]

    def side_of(chain, joints_only=False):
        # The largest X offset, from where the chain starts, of the joints and mesh centres of the
        # FIRST HALF of the chain: the shoulder/hip part that says which side a limb is on. Not the
        # whole chain - a hand reaching across the body would decide it - and not what hangs below
        # the chain, else a body bone would take the side of the first arm attached to it.
        ax = attach_point(chain)[0]
        dx = 0.0
        for b in chain[:max(2, (len(chain) + 1) // 2)]:
            points = [joints[b]]
            if vertices_by_bone[b] and not joints_only:
                points.append(_mean(vertices_by_bone[b]))
            for point in points:
                if abs(point[0] - ax) > abs(dx):
                    dx = point[0] - ax
        if abs(dx) > SIDE_THRESHOLD * height:
            return "R" if dx > 0 else "L"
        return "C"

    def number(chain, base):
        base_of_chain[chains.index(chain)] = base
        if len(chain) == 1:
            names[chain[0]] = base
        else:
            for i, b in enumerate(chain):
                names[b] = f"{base} {i + 1}"

    base_of_chain = {}     # chain index -> its name without the segment number
    on_root = [parents[parents[chain[0]]] < 0 for chain in chains]
    # The body: chains on the root that do not go sideways. Judged on the joints only - a torso's
    # mesh is often off-centre in a battle stance.
    trunk_ids = {i for i, chain in enumerate(chains) if on_root[i] and side_of(chain, True) == "C"}
    attached = [i for i, chain in enumerate(chains) if i not in trunk_ids
                and (on_root[i] or chain_of.get(parents[chain[0]]) in trunk_ids)]

    # The head, found before the sides (a head leaning in a fighting stance is off-centre): the
    # chain, among those attached on the body, holding the heaviest bone (most vertices) that sits
    # above where its chain starts.
    head_id, head_bone, head_weight = None, None, 0
    for i in attached:
        start_y = attach_point(chains[i])[1]
        for b in chains[i]:
            weight = len(vertices_by_bone[b])
            if weight > head_weight and _mean(vertices_by_bone[b])[1] > start_y:
                head_id, head_bone, head_weight = i, b, weight

    sides = {i: side_of(chains[i]) for i in attached if i != head_id}
    # Mirrored limbs: two chains on the same parent with the same shape (bone lengths, branching).
    # When the rest pose does not put them on two sides (a side-on stance spreads them front and
    # back), the file's own order decides: every vanilla skeleton stores the left one first.
    def shape(chain):
        bones = subtree(chain[0])
        return (len(chain), len(bones),
                tuple(round(lengths[b], 3) for b in sorted(bones)) if lengths else ())
    by_shape = {}
    for i in sides:
        by_shape.setdefault((parents[chains[i][0]], shape(chains[i])), []).append(i)
    for group in by_shape.values():
        if len(group) == 2 and sorted(sides[i] for i in group) != ["L", "R"]:
            left, right = sorted(group, key=lambda i: chains[i][0])
            sides[left], sides[right] = "L", "R"

    nested = []            # (chain index, index of the chain it branches off)
    trunk, centre, limbs = [], [], {"L": [], "R": []}
    for index, chain in enumerate(chains):
        if index in trunk_ids:
            trunk.append(chain)
        elif index == head_id:
            continue
        elif index in sides:
            (centre if sides[index] == "C" else limbs[sides[index]]).append(chain)
        else:
            nested.append((index, chain_of.get(parents[chain[0]])))

    # Body
    if len(trunk) == 1:
        number(trunk[0], "Body")
    elif len(trunk) == 2:
        upper, lower = sorted(trunk, key=lambda c: -_mean(subtree_points(c[0]))[1])
        number(upper, "Upper body")
        number(lower, "Lower body")
    else:
        for i, chain in enumerate(sorted(trunk, key=lambda c: -_mean(subtree_points(c[0]))[1])):
            number(chain, f"Body {_letters(i)}")

    # Head: the heavy bone, the neck above it, the tip (hair, ears...) past it
    if head_id is not None:
        head = chains[head_id]
        top = head.index(head_bone)
        for i, b in enumerate(head[:top]):
            names[b] = "Neck" if top == 1 else f"Neck {i + 1}"
        names[head_bone] = "Head"
        tip = head[top + 1:]
        for i, b in enumerate(tip):
            names[b] = "Head tip" if len(tip) == 1 else f"Head tip {i + 1}"
        base_of_chain[head_id] = "Head"

    # Limbs
    for side, side_limbs in limbs.items():
        kinds = {"leg": [], "arm": []}
        for chain in side_limbs:
            lowest = min(p[1] for p in subtree_points(chain[0]))
            kinds["leg" if lowest - min_y < GROUND_REACH * height else "arm"].append(chain)
        for kind, kind_chains in kinds.items():
            if kind == "leg":
                kind_chains.sort(key=lambda c: _mean(subtree_points(c[0]))[2])      # front first
            else:
                kind_chains.sort(key=lambda c: -_mean(subtree_points(c[0]))[1])     # top first
            for i, chain in enumerate(kind_chains):
                base = f"{side} {kind}" + (f" {_letters(i)}" if len(kind_chains) > 1 else "")
                number(chain, base)

    # Tails and other centred chains
    tails, rest = [], []
    for chain in centre:
        back = _mean(subtree_points(chain[0]))[2] - attach_point(chain)[2]
        (tails if back > TAIL_THRESHOLD * height else rest).append(chain)
    for group, word in ((tails, "Tail"), (rest, "Centre")):
        for i, chain in enumerate(group):
            number(chain, word + (f" {_letters(i)}" if len(group) > 1 else ""))

    # Branches off a named chain, resolved parents first (chain order follows bone order, and
    # a parent bone always has a lower id than its children in every vanilla file - but do not rely
    # on it: loop until nothing is left)
    pending = list(nested)
    letters_used = {}
    while pending:
        progressed = False
        for item in list(pending):
            index, parent_chain = item
            if parent_chain not in base_of_chain:
                continue
            parent_base = base_of_chain[parent_chain]
            letter = _letters(letters_used.get(parent_base, 0))
            letters_used[parent_base] = letters_used.get(parent_base, 0) + 1
            chain = chains[index]
            base = f"{parent_base} > {letter}"
            if len(chain) == 1:
                names[chain[0]] = base
            else:
                for i, b in enumerate(chain):
                    names[b] = f"{base}{i + 1}"
            base_of_chain[index] = base
            pending.remove(item)
            progressed = True
        if not progressed:
            for index, _ in pending:
                for b in chains[index]:
                    names[b] = f"Bone {b}"
            break

    for bone in range(nb):
        if parents[bone] < 0:
            names[bone] = ROOT_NAME if names[bone] is None else names[bone]
        elif names[bone] is None:
            names[bone] = f"Bone {bone}"
    return names
