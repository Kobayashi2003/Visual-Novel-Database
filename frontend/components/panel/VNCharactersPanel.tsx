import { VN } from "@/lib/types"
import { CharactersCardsGrid } from "@/components/card/CardsGrid"
import { ENUMS } from "@/lib/enums"

interface VNCharactersPanelProps {
  vn: VN
  spoilerLevel: "0" | "1" | "2"
  sexualLevel: "safe" | "suggestive" | "explicit"
  violenceLevel: "tame" | "violent" | "brutal"
}

export function VNCharactersPanel({ vn, spoilerLevel, sexualLevel, violenceLevel }: VNCharactersPanelProps) {

  const characters = vn.characters.map(character => ({
    ...character,
    role: character.vns.find(v => v.id === vn.id)?.role,
    spoiler: character.vns.find(v => v.id === vn.id)?.spoiler || 0
  }))
  const characterMain = characters.filter(c => c.role === 'main')
    .filter(c => c.spoiler <= parseInt(spoilerLevel))
    .sort((a, b) => a.name.localeCompare(b.name))
  const characterPrimary = characters.filter(c => c.role === 'primary')
    .filter(c => c.spoiler <= parseInt(spoilerLevel))
    .sort((a, b) => a.name.localeCompare(b.name))
  const characterSide = characters.filter(c => c.role === 'side')
    .filter(c => c.spoiler <= parseInt(spoilerLevel))
    .sort((a, b) => a.name.localeCompare(b.name))
  const characterAppears = characters.filter(c => c.role === 'appears')
    .filter(c => c.spoiler <= parseInt(spoilerLevel))
    .sort((a, b) => a.name.localeCompare(b.name))

  return (
    <div className="bg-[#0F2942]/80 backdrop-blur-md rounded-lg shadow-lg border border-white/10 p-4 flex flex-col gap-4">
      {characterMain.length > 0 && (
        <div>
          <h2 className="text-lg font-bold">{ENUMS.CHARACTER_ROLE.main}</h2>
          <CharactersCardsGrid characters={characterMain} cardType="image" layout="grid" sexualLevel={sexualLevel} violenceLevel={violenceLevel} />
        </div>
      )}
      {characterPrimary.length > 0 && (
        <div>
          <h2 className="text-lg font-bold">{ENUMS.CHARACTER_ROLE.primary}</h2>
          <CharactersCardsGrid characters={characterPrimary} cardType="image" layout="grid" sexualLevel={sexualLevel} violenceLevel={violenceLevel} />
        </div>
      )}
      {characterSide.length > 0 && (
        <div>
          <h2 className="text-lg font-bold">{ENUMS.CHARACTER_ROLE.side}</h2>
          <CharactersCardsGrid characters={characterSide} cardType="image" layout="grid" sexualLevel={sexualLevel} violenceLevel={violenceLevel} />
        </div>
      )}
      {characterAppears.length > 0 && (
        <div>
          <h2 className="text-lg font-bold">{ENUMS.CHARACTER_ROLE.appears}</h2>
          <CharactersCardsGrid characters={characterAppears} cardType="image" layout="grid" sexualLevel={sexualLevel} violenceLevel={violenceLevel} />
        </div>
      )}
    </div>
  )
}