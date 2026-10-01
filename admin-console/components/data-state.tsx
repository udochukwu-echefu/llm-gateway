export function DataState({ loading, error }: { loading: boolean; error?: string }) {
  if (error)
    return (
      <p role="alert" className="notice error">
        {error}
      </p>
    );
  if (loading)
    return (
      <div role="status" className="notice skeleton">
        Loading…
      </div>
    );
  return null;
}
