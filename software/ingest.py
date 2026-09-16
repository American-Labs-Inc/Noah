import os, re, requests, chromadb
from pypdf import PdfReader

LIBRARY = os.path.expanduser("~/emergency-library")
DB_PATH = os.path.expanduser("~/emergency-db")
OLLAMA = "http://localhost:11434"
CHUNK_SIZE = 900
OVERLAP = 150

_OBSOLETE = re.compile(
    r"(make|force|help|get) (him|her|them|the (person|child|baby|patient|kid|victim)"
    r"|a (person|child|baby)) (to )?(vomit|throw up)"
    r"|induce (vomiting|emesis)|to cause vomiting when"
    r"|(?:give|giving|gave|use|using|used|administer|administering|take|taking|took|with|dose of|doses of)\b[^.;]{0,40}?\bipecac"
    r"|\bipecac(?:\s+syrup)?\s*(?::|\d|should\b|must\b|can\b|may\b|will\b|is\b)(?!\s*(?:no longer|not|never|dangerous|outdated|obsolete|harmful|unsafe|contraindicated)\b)"
    r"|loosen the (tie|tourniquet) for a moment|let the blood circulate"
    r"|heel of your lower hand on (his|her|the) belly", re.I)
# A negation only exempts the phrase when it GOVERNS it. The scope rules live in
# safety.NEG_ATTACHED so all three filters agree: "do not give salt water or
# induce vomiting" is exempt, "loosen it every 15 minutes but never leave it
# off" is not.
from safety import NEG_ATTACHED as _OBSOLETE_NEG


def _is_obsolete(chunk):
    """Obsolete doctrine (emesis, tourniquet-loosening) stated as an instruction.
    Negated forms ('do NOT induce vomiting') are the CORRECT advice and must
    survive, but only a negation attached to the phrase itself counts."""
    for sent in re.split(r"(?<=[.!?\n])", chunk):
        for m in _OBSOLETE.finditer(sent):
            if not _OBSOLETE_NEG.search(sent[:m.start()]):
                return True
    return False


def read_document(path):
    if path.lower().endswith(".pdf"):
        reader = PdfReader(path)
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    if path.lower().endswith(".txt"):
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    return None

def chunk_text(text):
    chunks = []
    start = 0
    while start < len(text):
        end = start + CHUNK_SIZE
        cut = text.rfind("\n", start + CHUNK_SIZE - 200, end)
        if cut == -1 or cut <= start:
            cut = end
        chunk = text[start:cut].strip()
        if len(chunk) > 100:
            chunks.append(chunk)
        start = max(cut - OVERLAP, start + 1)
    return chunks

def embed(texts):
    r = requests.post(f"{OLLAMA}/api/embed",
                      json={"model": "nomic-embed-text", "input": texts})
    r.raise_for_status()
    return r.json()["embeddings"]

client = chromadb.PersistentClient(path=DB_PATH)
try:
    client.delete_collection("emergency")
except Exception:
    pass
col = client.create_collection("emergency")

total = 0
for fname in sorted(os.listdir(LIBRARY)):
    path = os.path.join(LIBRARY, fname)
    if not os.path.isfile(path):
        continue
    try:
        text = read_document(path)
    except Exception as e:                       # one bad PDF must not abort the build
        print(f"SKIP {fname} (unreadable: {e})")
        continue
    if not text or len(text) < 500:
        print(f"SKIP {fname} (no usable text)")
        continue
    chunks = chunk_text(text)
    if "IFRC" not in fname:
        kept = [c for c in chunks if not _is_obsolete(c)]
        if len(kept) != len(chunks):
            print(f"  BLOCKED {len(chunks)-len(kept)} obsolete-doctrine chunks from {fname}")
        chunks = kept
    print(f"{fname}: {len(chunks)} chunks, embedding...")
    for i in range(0, len(chunks), 16):
        batch = chunks[i:i+16]
        vectors = embed(batch)
        ids = [f"{fname}-{i+j}" for j in range(len(batch))]
        metas = [{"source": fname} for _ in batch]
        col.add(ids=ids, embeddings=vectors, documents=batch, metadatas=metas)
        print(f"  {min(i+16, len(chunks))}/{len(chunks)}")
    total += len(chunks)

print(f"\nDone. {total} chunks indexed into {DB_PATH}")
