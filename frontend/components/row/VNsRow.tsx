import Link from "next/link"
import { Row } from "@/components/row/Row"

interface VN {
  id: string
  role: string
  title: string
  release?: {
    id: string
    title: string
  }
}

interface VNsRowProps {
  vns: VN[]
}

export function VNsRow({ vns }: VNsRowProps) {
  if (vns.length === 0) return null

  const groupedVNs = vns.reduce((groups, vn) => {
    if (!groups[vn.title]) {
      groups[vn.title] = []
    }
    groups[vn.title].push(vn)
    return groups
  }, {} as Record<string, VN[]>)

  const sortedGroups = Object.entries(groupedVNs).sort(([a], [b]) => a.localeCompare(b))

  return (
    <></>
  )
}