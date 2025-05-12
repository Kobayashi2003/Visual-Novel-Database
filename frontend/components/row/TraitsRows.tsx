import Link from "next/link"
import { Row } from "@/components/row/Row"

interface Trait {
  id: string
  name: string
  group_id?: string
  group_name?: string
  spoiler: number
  lie: boolean
}

interface TraitsRowProps {
  traits: Trait[]
  showSexual: boolean
  spoilerLevel: number
}

export function TraitsRow({ traits, showSexual, spoilerLevel }: TraitsRowProps) {

  if (traits.length === 0) return null

  const groupedTraits = traits.reduce((groups, trait) => {
    if (!trait.group_id || !trait.group_name) return groups
    const isSexualTrait = trait.group_name.toLowerCase().includes("sexual") ?? false
    if ((showSexual || !isSexualTrait) && (trait.spoiler <= spoilerLevel)) {
      if (!groups[trait.group_id]) {
        groups[trait.group_id] = { name: trait.group_name, traits: [] }
      }
      groups[trait.group_id].traits.push(trait)
    }
    return groups
  }, {} as Record<string, { name: string; traits: Trait[] }>)

  const sortedGroups = Object.entries(groupedTraits).sort(([a], [b]) => a.localeCompare(b))

  return (
    <div className="flex flex-col gap-2">
      {sortedGroups.map(([groupId, { name, traits }]) => (
        <Row key={groupId} label={name} value={
          <div className="flex flex-wrap gap-1 items-center">
            {traits.map((trait, index) => (
              <div key={trait.id}>
                <Link href={`/${trait.id}`} className="text-blue-400 hover:text-blue-500 transition-colors">
                  {trait.name}
                </Link>
                {index < traits.length - 1 && <span className="text-white/20 mx-1">•</span>}
              </div>
            ))}
          </div>
        } />
      ))}
    </div>
  )
}
