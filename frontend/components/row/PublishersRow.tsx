import Link from "next/link"
import { cn } from "@/lib/utils"
import { Row } from "@/components/row/Row"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { ICON } from "@/lib/icons"
import { ENUMS } from "@/lib/enums"

interface Publisher {
  id: string
  name: string
  original?: string
  languages: string[]
}

interface PublishersRowProps {
  publishers: Publisher[]
}

export function PublishersRow({ publishers }: PublishersRowProps) {

  if (publishers.length === 0) return null

  const groupedPublishers = publishers.reduce(
    (groups, publisher) => {
      for (const language of publisher.languages) {
        const group = language || 'other'
        if (!groups[group]) {
          groups[group] = []
        }
        groups[group].push(publisher)
      }
      return groups
    },
    {} as Record<string, Publisher[]>
  )

  return (
    <Row label="Publishers" value={
      <div className="flex flex-col gap-1">
        {Object.entries(groupedPublishers).map(([group, items]) => (
          <div key={group} className="flex gap-1 items-center">
            <Tooltip>
              <TooltipTrigger asChild>
                <span className={cn(
                  ICON.LANGUAGE[group as keyof typeof ICON.LANGUAGE]
                )} />
              </TooltipTrigger>
              <TooltipContent className="bg-black/50 text-white text-xs">
                {ENUMS.LANGUAGE[group as keyof typeof ENUMS.LANGUAGE]}
              </TooltipContent>
            </Tooltip>
            <div className="flex flex-wrap gap-1 items-center">
              {items.map((item, index) => (
                <div key={item.id}>
                  <Link href={`/${item.id}`} className="text-blue-400 hover:text-blue-500 transition-colors">
                    {item.name}
                  </Link>
                  {index < items.length - 1 && <span className="px-1">&</span>}
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    } />
  )
}