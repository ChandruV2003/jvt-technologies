export function App() {
  return (
    <main style={{ fontFamily: "Georgia, serif", margin: "3rem auto", maxWidth: 900, lineHeight: 1.5 }}>
      <h1>Private Document Intelligence Demo</h1>
      <p>
        Local-first scaffold for uploading matter documents, retrieving grounded passages, and returning
        citation-backed answers.
      </p>
      <section>
        <h2>Planned flow</h2>
        <ol>
          <li>Upload documents into a client-scoped workspace.</li>
          <li>Extract text, metadata, and chunk boundaries.</li>
          <li>Store embeddings in a local vector backend.</li>
          <li>Answer questions with cited source passages.</li>
        </ol>
      </section>
    </main>
  );
}
