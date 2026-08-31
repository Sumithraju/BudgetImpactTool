type SearchBoxProps = {
  onSearch: (query: string) => void;
};

export function SearchBox({ onSearch }: SearchBoxProps) {
  return (
    <div className="evitrack-search">
      <input
        type="search"
        placeholder="Search for prevalence, population, costs, efficacy..."
        onKeyDown={(event) => {
          if (event.key === "Enter") {
            onSearch(event.currentTarget.value.trim());
          }
        }}
      />

      <button
        type="button"
        onClick={(event) => {
          const input = event.currentTarget
            .previousElementSibling as HTMLInputElement | null;

          onSearch(input?.value.trim() ?? "");
        }}
      >
        Search
      </button>
    </div>
  );
}
