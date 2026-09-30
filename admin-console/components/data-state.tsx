export function DataState({ loading, error }: { loading: boolean; error?: string }) {
  if (error)
    return (
      <p role="alert" className="notice error">
        {error}
      </p>
    );
  if (loading)
    return (
      <p role="status" className="notice">
        Loading…
      </p>
    );
  return null;
}
