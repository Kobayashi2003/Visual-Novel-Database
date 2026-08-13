/** Tag detail page (catalog kind): info sidebar + description + paginated tagged VNs. */
"use client"

import { useState } from "react"
import { api } from "@/lib/api"
import { enumLabel } from "@/lib/enums"
import type { Tag } from "@/lib/types"
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
import { VNsCardsGrid } from "@/components/card/CardsGrid"
import { TagInfoPanel } from "./TagInfoPanel"

interface TagDetailPageProps {
  id: number
}

export function TagDetailPage({ id }: TagDetailPageProps) {
  const { data: tag, loading, error } = useEntity<Tag>(id, api.by_id.tag)
  const { defaultSexualLevel, defaultViolenceLevel } = useUserContext()
  const [sexualLevel, setSexualLevel] = useState(defaultSexualLevel)
  const [violenceLevel, setViolenceLevel] = useState(defaultViolenceLevel)

  // Original-text mode: localise the name (transserve dictionary) and the
  // description (transserve passage memory) to Japanese, each falling back to
  // the original English while loading or when no translation exists.
  const { showOriginal } = useSearchContext()
  const translateName = useTerm(tag ? [tag.name] : [], showOriginal)
  const description = usePassage(tag?.description, showOriginal)

  if (loading || error || !tag) return <DetailStatus loading={loading} error={error} />

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
          title={translateName(tag.name)}
          subtitle={tag.category && (
            <p className="text-sm text-muted mt-0.5">{enumLabel('CATEGORY', tag.category)}</p>
          )}
        />
      }
      aside={<>{levelSelectors("col")}<TagInfoPanel tag={tag} /></>}
      inlineAside={<>{levelSelectors("row")}<TagInfoPanel tag={tag} inline /></>}
    >
      <div className="flex flex-col gap-6">
        {description && (
          <Section title="Description">
            <BBCodeText text={description} collapsible />
          </Section>
        )}

        <Section title={`Visual Novels (${tag.vn_count.toLocaleString()})`}>
          <EntityCardSection
            query={{ tag: tag.id, sort: "rating", reverse: true }}
            fetcher={api.small.vn}
            renderGrid={vns => (
              <VNsCardsGrid
                vns={vns} layout="grid" cardType="image"
                sexualLevel={sexualLevel} violenceLevel={violenceLevel}
              />
            )}
            loadingMessage="Loading visual novels..."
            emptyMessage="No visual novels listed."
          />
        </Section>
      </div>
    </DetailShell>
  )
}
