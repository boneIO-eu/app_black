# EntitySelectDropdown — Reusable Entity Selector

## Overview

`EntitySelectDropdown` is a reusable Select component for choosing any type of entity (outputs, covers, binary sensors, etc.) with a rich display showing:
- **Entity name** (bold)
- **Entity ID** (subtitle, when different from name)
- **Area** (📍 icon with area name)
- **Badges** (e.g. "Group" for output groups)
- **Disabled state** (grayed out + warning badge for unsaved items)

## Location

`frontend/src/components/UISettings/EntitySelectDropdown.tsx`

## Interface

```ts
interface EntityItem {
  id: string;           // Unique identifier
  name: string;         // Display name
  area?: string;        // Area ID (resolved via allAreas)
  badge?: string;       // Badge label (e.g. "Group")
  badgeClass?: string;  // Badge CSS class (default: badge-secondary)
  disabled?: boolean;   // Disable selection (e.g. unsaved items)
  disabledLabel?: string; // Warning badge text when disabled
}

interface EntitySelectDropdownProps {
  value: string;
  onChange: (value: string) => void;
  items: EntityItem[];
  allAreas?: AreaEntity[];
  placeholder?: string;
  excludeIds?: string[];
  compact?: boolean;     // Use smaller trigger height
}
```

## Usage Examples

### In ActionConditions (state condition entity selection)
```tsx
<EntitySelectDropdown
  value={condition.entity_id || ''}
  onChange={(value) => updateSingleCondition(index, 'entity_id', value)}
  items={getEntityItems(condition.entity)}
  allAreas={allAreas}
  placeholder={t('event_form.condition_entity_id')}
  compact
/>
```

### In OutputAction (output selection with groups)
```tsx
const outputItems: EntityItem[] = useMemo(() => {
  const outputs = allOutputs.map(o => ({
    id: o.id, name: o.name || o.id, area: o.area,
    disabled: !isSaved(o.id), disabledLabel: 'Unsaved',
  }));
  const groups = allOutputGroups.map(g => ({
    id: g.id, name: g.name || g.id, badge: 'Group',
    disabled: !isSaved(g.id),
  }));
  return [...outputs, ...groups];
}, [allOutputs, allOutputGroups, savedOutputs]);

<EntitySelectDropdown
  value={action.boneio_output || ''}
  onChange={(value) => handleUpdate('boneio_output', value)}
  items={outputItems}
  placeholder={t('event_form.select_output')}
/>
```

## Files Changed

| File | Change |
|---|---|
| `EntitySelectDropdown.tsx` | **New** — reusable entity selector |
| `ActionConditions.tsx` | Uses `EntitySelectDropdown` for entity_id, added `allAreas` prop |
| `ActionFields.tsx` | Passes `allAreas` to `ActionConditions` |
| `OutputAction.tsx` | Refactored from `OutputSelectDropdown` to `EntitySelectDropdown` |

## Migration Notes

- `OutputSelectDropdown` is **kept** for backward compatibility (5 other files still use it)
- New code should prefer `EntitySelectDropdown` 
- `OutputSelectDropdown` can be gradually migrated in follow-up PRs
