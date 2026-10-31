"""Small deterministic latent-semantic index, with no downloaded model/runtime.

The corpus supplies the meaning relationships. Query expansion from the client
can add concepts absent from the vocabulary; results always retain source text.
"""

from collections import Counter
import math
import re
import unicodedata


_STOP = set(
    "a an and are as at be been but by can for from had has have how i in into is it its of on or that the their them there these this to was were what when which who will with you your answer".split()
)


def tokens(text):
    return [
        word for word in re.findall(r"[^\W_]{2,}", unicodedata.normalize("NFKC", text).casefold()) if word not in _STOP
    ]


def unit(vector):
    length = math.sqrt(sum(value * value for value in vector))
    return [value / length for value in vector] if length > 1e-12 else [0.0] * len(vector)


def build_model(documents, check=lambda: None):
    keys = sorted(documents)
    counts = [Counter(tokens(documents[key]["text"])).most_common(64) for key in keys]
    frequencies = Counter(word for row in counts for word, _ in row)
    vocabulary = sorted(frequencies, key=lambda word: (-frequencies[word], word))[:2048]
    positions = {word: index for index, word in enumerate(vocabulary)}
    idf = [math.log(1 + len(keys) / (1 + frequencies[word])) + 1 for word in vocabulary]
    rows = []
    for row in counts:
        values = {
            positions[word]: (1 + math.log(count)) * idf[positions[word]] for word, count in row if word in positions
        }
        norm = math.sqrt(sum(value * value for value in values.values())) or 1
        rows.append({index: value / norm for index, value in values.items()})
    rank = min(8, max(1, int(math.sqrt(len(keys)) / 2)), len(vocabulary))
    basis = []
    for axis in range(rank):
        vector = unit([math.sin((index + 1) * (axis + 1) * 1.61803398875) for index in range(len(vocabulary))])
        for _ in range(12):
            check()
            projected = [sum(value * vector[index] for index, value in row.items()) for row in rows]
            next_vector = [0.0] * len(vocabulary)
            for row, weight in zip(rows, projected):
                for index, value in row.items():
                    next_vector[index] += value * weight
            for previous in basis:
                product = sum(a * b for a, b in zip(previous, next_vector))
                next_vector = [a - product * b for a, b in zip(next_vector, previous)]
            vector = unit(next_vector)
        if any(abs(value) > 1e-10 for value in vector):
            basis.append(vector)
    embeddings = {
        key: [
            round(value, 8)
            for value in unit([sum(weight * vector[index] for index, weight in row.items()) for vector in basis])
        ]
        for key, row in zip(keys, rows)
    }
    return {
        "vocabulary": vocabulary,
        "idf": idf,
        "basis": [[round(value, 8) for value in vector] for vector in basis],
        "embeddings": embeddings,
        "engine": "local_latent_semantic_indexing",
    }


def rank(model, documents, query, related_terms=()):
    positions = {word: index for index, word in enumerate(model["vocabulary"])}
    terms = Counter(tokens(" ".join([query, *related_terms])))
    weights = {
        positions[word]: (1 + math.log(count)) * model["idf"][positions[word]]
        for word, count in terms.items()
        if word in positions
    }
    projected = unit([sum(value * vector[index] for index, value in weights.items()) for vector in model["basis"]])
    results = []
    for key, entry in documents.items():
        semantic = max(0, sum(a * b for a, b in zip(projected, model["embeddings"].get(key, []))))
        found = set(tokens(entry["text"]))
        lexical = len(found & set(terms)) / max(1, len(terms))
        score = 0.7 * semantic + 0.3 * lexical
        if score > 1e-6:
            results.append((score, key))
    return sorted(results, key=lambda pair: (-pair[0], pair[1]))
