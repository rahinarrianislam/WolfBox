from .handlers import list_docs


def search(store, query, k=2):
    terms = set(query.lower().split())
    matches = []
    for doc in list_docs(store, {})["docs"]:
        text = store.read_text(f"courses/{doc['course']}/docs/{doc['item_id']}/text.md", "") or ""
        words = set(text.lower().split())
        score = len(terms & words)
        if score:
            snippet = next((line for line in text.splitlines() if any(t in line.lower() for t in terms)), text[:240])
            matches.append((score, {"doc_id": doc["doc_id"], "title": doc["title"], "snippet": snippet[:240]}))
    return [row for _, row in sorted(matches, key=lambda pair: -pair[0])[:k]]
