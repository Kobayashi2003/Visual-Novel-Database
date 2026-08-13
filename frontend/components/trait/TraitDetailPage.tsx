/** Trait detail page (catalog kind): info sidebar + description + paginated
 *  characters with the trait. */
"use client"

import { useState } from "react"
import { api } from "@/lib/api"
import type { Trait } from "@/lib/types"
import { useEntity } from "@/hooks/useEntity"
import { useUserContext } from "@/context/UserContext"
import { useSearchContext } from "@/context/SearchContext"
import { useTerm } from "@/hooks/useTerm"
import { usePassage } from "@/hooks/usePassage"
import { DetailShell, DetailStatus } from "@/components/detail/DetailShell"
import { DetailHeader } from "@/components/detail/DetailHeader"
import { Section } from "@/components/detail/InfoPrimitives"
import { ContentLevelSelectors } from "@/components/common/ContentLevelSelectors"
import { BBCodeText } from "@/components/common/BBCodeText"
import { EntityCardSection } from "@/components/common/EntityCardSection"
import { CharactersCardsGrid } from "@/components/card/CardsGrid"
import { TraitInfoPanel } from "./TraitInfoPanel"

interface TraitDetailPageProps {
  id: number
}

export function TraitDetailPage({ id }: TraitDetailPageProps) {
  const { data: trait, loading, error } = useEntity<Trait>(id, api.by_id.trait)
  const { defaultSexualLevel, defaultViolenceLevel } = useUserContext()
  const [sexualLevel, setSexualLevel] = useState(defaultSexualLevel)
  const [violenceLevel, setViolenceLevel] = useState(defaultViolenceLevel)

  // Original-text mode: localise the name and group name (transserve dictionary)
  // and the description (transserve passage memory) to Japanese, each falling
  // back to the original English while loading or when no translation exists.
  const { showOriginal } = useSearchContext()
  const translateName = useTerm(
    trait ? [trait.name, ...(trait.group_name ? [trait.group_name] : [])] : [],
    showOriginal,
  )
  const description = usePassage(trait?.description, showOriginal)

  if (loading || error || !trait) return <DetailStatus loading={loading} error={error} />

  const levelSelectors = (direction: "row" | "col") => (
    <ContentLevelSelectors
      direction={direction}
      sexualLevel={sexualLevel} setSexualLevel={setSexualLevel}
      violenceLevel={violenceLevel} setViolenceLevel={setViolenceLevel}
    />
  )

  return (
    <DetailShell
      header={
        <DetailHeader
          title={translateName(trait.name)}
          subtitle={trait.group_name && (
            <p className="text-sm text-muted mt-0.5">{translateName(trait.group_name)}</p>
          )}
        />
      }
      aside={<>{levelSelectors("col")}<TraitInfoPanel trait={trait} /></>}
      inlineAside={<>{levelSelectors("row")}<TraitInfoPanel trait={trait} inline /></>}
    >
      <div className="flex flex-col gap-6">
        {description && (
          <Section title="Description">
            <BBCodeText text={description} collapsible />
          </Section>
        )}

        <Section title={`Characters (${trait.char_count.toLocaleString()})`}>
          <EntityCardSection
            query={{ trait: trait.id }}
            fetcher={api.small.character}
            renderGrid={characters => (
              <CharactersCardsGrid
                characters={characters} layout="grid" cardType="image"
                sexualLevel={sexualLevel} violenceLevel={violenceLevel}
              />
            )}
            loadingMessage="Loading characters..."
            emptyMessage="No characters listed."
          />
        </Section>
      </div>
    </DetailShell>
  )
}
