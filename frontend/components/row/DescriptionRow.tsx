import { Row2 } from "@/components/row/Row2"

interface DescriptionRowProps {
  description?: string
}

export function DescriptionRow({ description }: DescriptionRowProps) {
  if (!description) return null

  return (
    <Row2 label="Description" value={description} />
  )
}
