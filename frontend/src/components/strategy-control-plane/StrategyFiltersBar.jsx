import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export const StrategyFiltersBar = ({
  listFilters,
  setListFilters,
  filterOptions,
  tagSearchText,
  setTagSearchText,
  selectedTagFilters,
  setSelectedTagFilters,
  activeFilterChips,
  savedFilterName,
  setSavedFilterName,
  savedFilters,
  onApplyFilters,
  onApplyRolePreset,
  onClearAllFilters,
  onSaveCurrentFilterSet,
  onApplySavedFilterSet,
}) => {
  return (
    <div className="mt-2 grid gap-2" data-testid="admin-strategies-filter-toolbar">
      <Input
        placeholder="search code/name/owner"
        value={listFilters.search}
        onChange={(e) => setListFilters((prev) => ({ ...prev, search: e.target.value, page: 1 }))}
        data-testid="admin-strategies-filter-search-input"
      />

      <div className="grid grid-cols-2 gap-2">
        <Input
          placeholder="category"
          value={listFilters.category}
          onChange={(e) => setListFilters((prev) => ({ ...prev, category: e.target.value, page: 1 }))}
          data-testid="admin-strategies-filter-category-input"
          list="admin-strategies-category-options"
        />
        <datalist id="admin-strategies-category-options">
          {(filterOptions.categories || []).map((item) => (
            <option key={item} value={item} />
          ))}
        </datalist>

        <Input
          placeholder="lifecycle_state"
          value={listFilters.lifecycle_state}
          onChange={(e) => setListFilters((prev) => ({ ...prev, lifecycle_state: e.target.value, page: 1 }))}
          data-testid="admin-strategies-filter-lifecycle-input"
        />
      </div>

      <div className="grid grid-cols-2 gap-2">
        <Input
          placeholder="validation_status"
          value={listFilters.validation_status}
          onChange={(e) => setListFilters((prev) => ({ ...prev, validation_status: e.target.value, page: 1 }))}
          data-testid="admin-strategies-filter-validation-input"
        />
        <Input
          placeholder="status"
          value={listFilters.status_filter}
          onChange={(e) => setListFilters((prev) => ({ ...prev, status_filter: e.target.value, page: 1 }))}
          data-testid="admin-strategies-filter-status-input"
        />
      </div>

      <div className="grid grid-cols-2 gap-2">
        <Input
          placeholder="owner filter"
          value={listFilters.owner_name}
          onChange={(e) => setListFilters((prev) => ({ ...prev, owner_name: e.target.value, page: 1 }))}
          data-testid="admin-strategies-filter-owner-input"
          list="admin-strategies-owner-options"
        />
        <datalist id="admin-strategies-owner-options">
          {(filterOptions.owner_names || []).map((item) => (
            <option key={item} value={item} />
          ))}
        </datalist>

        <Input
          placeholder="tag search"
          value={tagSearchText}
          onChange={(e) => setTagSearchText(e.target.value)}
          data-testid="admin-strategies-filter-tag-search-input"
        />
      </div>

      <div className="flex flex-wrap gap-2" data-testid="admin-strategies-filter-tag-multiselect">
        {(filterOptions.tags || [])
          .filter((tag) => {
            const query = String(tagSearchText || "").trim().toLowerCase();
            if (!query) return true;
            return String(tag || "").toLowerCase().includes(query);
          })
          .slice(0, 20)
          .map((tag) => {
            const selected = selectedTagFilters.includes(tag);
            return (
              <Button
                key={tag}
                type="button"
                variant="outline"
                className={selected ? "border-orange-500 text-orange-200" : "border-slate-600 text-slate-200"}
                onClick={() => {
                  setSelectedTagFilters((prev) =>
                    prev.includes(tag) ? prev.filter((item) => item !== tag) : [...prev, tag],
                  );
                }}
                data-testid={`admin-strategies-filter-tag-toggle-${tag}`}
              >
                {tag}
              </Button>
            );
          })}
      </div>

      {selectedTagFilters.length > 0 && (
        <div className="flex flex-wrap gap-2" data-testid="admin-strategies-selected-tag-chips">
          {selectedTagFilters.map((tag) => (
            <button
              key={`selected-${tag}`}
              type="button"
              className="rounded-full border border-orange-500 px-2 py-1 text-[10px] uppercase tracking-wide text-orange-200"
              onClick={() => setSelectedTagFilters((prev) => prev.filter((item) => item !== tag))}
              data-testid={`admin-strategies-selected-tag-remove-${tag}`}
              title="Tag filtresini kaldır"
            >
              {tag} ×
            </button>
          ))}
        </div>
      )}

      <div className="grid grid-cols-2 gap-2">
        <Input
          placeholder="sort_by"
          value={listFilters.sort_by}
          onChange={(e) => setListFilters((prev) => ({ ...prev, sort_by: e.target.value }))}
          data-testid="admin-strategies-filter-sort-by-input"
        />
        <Input
          placeholder="sort_order asc/desc"
          value={listFilters.sort_order}
          onChange={(e) => setListFilters((prev) => ({ ...prev, sort_order: e.target.value }))}
          data-testid="admin-strategies-filter-sort-order-input"
        />
      </div>

      <div className="flex flex-wrap gap-2" data-testid="admin-strategies-filter-actions-row">
        <Button variant="outline" className="border-slate-500 text-slate-100" onClick={() => setListFilters((prev) => ({ ...prev, active_only: !prev.active_only }))} data-testid="admin-strategies-filter-active-toggle-button">active_only: {String(Boolean(listFilters.active_only))}</Button>
        <Button variant="outline" className="border-slate-500 text-slate-100" onClick={() => setListFilters((prev) => ({ ...prev, production_only: !prev.production_only }))} data-testid="admin-strategies-filter-production-toggle-button">production_only: {String(Boolean(listFilters.production_only))}</Button>
        <Button variant="outline" className="border-slate-500 text-slate-100" onClick={onApplyFilters} data-testid="admin-strategies-filter-apply-button">Apply Filters</Button>
        <Button variant="outline" className="border-sky-500 text-sky-200" onClick={() => onApplyRolePreset("desk")} data-testid="admin-strategies-role-preset-desk-button">Preset: Desk</Button>
        <Button variant="outline" className="border-sky-500 text-sky-200" onClick={() => onApplyRolePreset("ops")} data-testid="admin-strategies-role-preset-ops-button">Preset: Ops</Button>
        <Button variant="outline" className="border-sky-500 text-sky-200" onClick={() => onApplyRolePreset("admin")} data-testid="admin-strategies-role-preset-admin-button">Preset: Admin</Button>
        <Button variant="outline" className="border-red-500 text-red-200" onClick={onClearAllFilters} data-testid="admin-strategies-filter-clear-all-button">Clear All</Button>
      </div>

      {activeFilterChips.length > 0 && (
        <div className="flex flex-wrap gap-2" data-testid="admin-strategies-active-filter-chips">
          {activeFilterChips.map((chip) => (
            <span key={chip.key} className="rounded-full border border-orange-500 px-2 py-1 text-[10px] uppercase tracking-wide text-orange-200" data-testid={`admin-strategies-filter-chip-${chip.key}`}>
              {chip.label}
            </span>
          ))}
        </div>
      )}

      <div className="grid grid-cols-2 gap-2" data-testid="admin-strategies-saved-filter-row">
        <Input
          placeholder="saved filter name"
          value={savedFilterName}
          onChange={(e) => setSavedFilterName(e.target.value)}
          data-testid="admin-strategies-saved-filter-name-input"
        />
        <Button variant="outline" className="border-slate-500 text-slate-100" onClick={onSaveCurrentFilterSet} data-testid="admin-strategies-saved-filter-save-button">Save Current Filter</Button>
      </div>

      {Object.keys(savedFilters).length > 0 && (
        <div className="flex flex-wrap gap-2" data-testid="admin-strategies-saved-filter-buttons">
          {Object.keys(savedFilters).map((key) => (
            <Button
              key={key}
              variant="outline"
              className="border-slate-500 text-slate-100"
              onClick={() => onApplySavedFilterSet(key)}
              data-testid={`admin-strategies-saved-filter-apply-${key}`}
            >
              {key}
            </Button>
          ))}
        </div>
      )}
    </div>
  );
};
