"""Optional, experiment-local interventions on composition source profiles.

Keep source-model changes here, separate from sampling and statistical decisions.
Each adapter returns serializable evidence of exactly what it changed.
"""
import json
from copy import deepcopy

from maude_hcs.generate_cp3 import distribute_profiles


def independent_hashtags(directory, population, profile):
    """Give every Mastodon instance a disjoint, equal-length hashtag vocabulary.

Apply the same renaming to the single arm. Preserving lengths and vocabulary
size avoids changing packet sizes or tag-selection probabilities as a side effect.
The shared server, user actions, images and network remain unchanged.
"""
    profile_dir = directory / 'tgen_user_models' / 'mastodon'
    original = json.loads((profile_dir / f'{profile}.json').read_text())
    tags = original['parameters']['hashtags']
    if (not isinstance(tags, list) or not tags or any(not isinstance(tag, str) or not tag.isascii() or not tag.isalpha()
                        for tag in tags) or len(set(tags)) != len(tags)):
        raise ValueError('Hashtag isolation requires distinct nonempty ASCII alphabetic hashtags')
    assignments = []
    for instance in range(population):
        renamed = []
        for index, tag in enumerate(tags):
            value = instance * len(tags) + index
            if value >= 26 ** len(tag):
                raise ValueError('Population exceeds the available equal-length hashtag namespace')
            letters = []
            for _ in tag:
                letters.append(chr(ord('a') + value % 26))
                value //= 26
            renamed.append(''.join(reversed(letters)))
        assignments.append(renamed)

    derived = {}
    for index, tags in enumerate(assignments, start=1):
        name = f'{profile}_isolated_{index}'
        path = profile_dir / f'{name}.json'
        if path.exists():
            raise ValueError(f'Derived profile already exists: {path}')
        model = deepcopy(original)
        model['parameters']['hashtags'] = tags
        path.write_text(json.dumps(model, indent=2) + '\n')
        derived[name] = model

    # The generator's distribute_profiles is deterministic: each 1/N weight
    # yields exactly one instance, in insertion order. Verify that contract so
    # a future generator change cannot silently give two clients the same tags.
    weights = {name: 1 / population for name in derived}
    assigned = distribute_profiles(population, list(weights.items()))
    if assigned != list(derived):
        raise ValueError('Generator did not assign one distinct profile per instance')
    return dict(profile_weights=weights, profiles_by_instance=assigned,
                derived_profiles=derived)


# New interventions register their supported kind and adapter here. Unknown or
# incompatible interventions are rejected before any simulations are started.
INTERVENTIONS = {'independent_hashtags': ('masTgen', independent_hashtags)}


def validate_intervention(name, tgen_type):
    if not isinstance(name, str) or (name != 'none' and
            (name not in INTERVENTIONS or INTERVENTIONS[name][0] != tgen_type)):
        raise ValueError(f'Unsupported intervention {name!r} for {tgen_type}')


def apply_intervention(name, tgen_type, directory, population, profile, placement):
    validate_intervention(name, tgen_type)
    details = {} if name == 'none' else INTERVENTIONS[name][1](directory, population, profile)
    if details:
        placement['profiles'] = details.pop('profile_weights')
    evidence = dict(name=name, **details)
    (directory / 'composition-intervention.json').write_text(json.dumps(evidence, indent=2) + '\n')
    return evidence
