import Link from "next/link"
import { Row } from "@/components/row/Row"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"

interface SeiyuuRowProps {
  seiyuu: Array<{
    id: string
    name: string
    original?: string
    note?: string
  }>
}

export function SeiyuuRow({ seiyuu }: SeiyuuRowProps) {
  if (seiyuu.length === 0) return null

  return (
    <Row label="Seiyuu" value={
      <div className="flex flex-col gap-1">
        {seiyuu.map((seiyuu) => (
          <div key={seiyuu.id} className="flex gap-1 items-center">
            <Tooltip>
              <TooltipTrigger asChild>
                <Link href={`/${seiyuu.id}`} className="text-blue-400 hover:text-blue-500 transition-colors">
                  {seiyuu.name}
                </Link>
              </TooltipTrigger>
              <TooltipContent className="bg-black/50 text-white text-xs">
                {seiyuu.original || seiyuu.name}
              </TooltipContent>
            </Tooltip>
            {seiyuu.note && (
              <p className="text-white/60 text-xs">
                ({seiyuu.note})
              </p>
            )}
          </div>
        ))}
      </div>
    } />
  )
}
