import { cn } from "@/lib/utils"
import { Image } from "@/components/image/Image"
import { Row } from "@/components/row/Row"
import { SeiyuuRow } from "@/components/row/SeiyuuRow"
import { TraitsRow } from "@/components/row/TraitsRows"
import { DescriptionRow } from "@/components/row/DescriptionRow"
import { Character } from "@/lib/types"

import { AlertTriangle, ImageOff } from "lucide-react"

interface CharacterDetailsPanelProps {
  character: Character
  spoilerLevel: "0" | "1" | "2"
  sexualLevel: "safe" | "suggestive" | "explicit"
  violenceLevel: "tame" | "violent" | "brutal"
}

export function CharacterDetailsPanel({ character, spoilerLevel, sexualLevel, violenceLevel }: CharacterDetailsPanelProps) {

  const mainTitle = character.name
  const subTitle = character.original || ""
  const image_url = character.image?.url
  const image_dims = character.image?.dims
  const image_sexual = character.image?.sexual || 0
  const image_violence = character.image?.violence || 0
  const red_alert = (sexualLevel !== "explicit" && image_sexual > 1) || (violenceLevel !== "brutal" && image_violence > 1)
  const yellow_alert = (sexualLevel === "safe" && image_sexual > 0.5) || (violenceLevel === "tame" && image_violence > 0.5)

  const sex = character.sex
  const measurements = [
    character.height && `Height: ${character.height}cm`,
    character.weight && `Weight: ${character.weight}kg`,
    character.bust && character.waist && character.hips &&
    `Bust-Waist-Hips: ${character.bust}-${character.waist}-${character.hips}cm`,
    character.cup && `${character.cup} cup`,
    character.blood_type && `Blood Type: ${character.blood_type.toUpperCase()}`
  ].filter(Boolean).join(", ")
  const birthday = (character.birthday) &&
    new Date(`2000-${character.birthday[0].toString().padStart(2, "0")}-${character.birthday[1].toString().padStart(2, "0")}`)
      .toLocaleDateString("en-US", {
        month: "long",
        day: "numeric",
      })
  const seiyuu = character.seiyuu
  const traits = character.traits
  const vns = character.vns
  const description = character.description

  return (
    <div className="flex flex-col gap-4 bg-[#0F2942]/80 backdrop-blur-md rounded-lg shadow-lg border border-white/10 p-4 md:p-8">
      <div>
        {/* TITLE */}
        <h1 className="text-2xl font-bold">{mainTitle}</h1>
        <h2 className="text-sm text-gray-500">{subTitle}</h2>
      </div>
      <div className={cn(
        "grid",
        image_url && "md:grid-cols-[250px_1fr]"
      )}>
        {/* IMAGE */}
        {red_alert ? (
          <div className="flex items-center justify-center">
            <AlertTriangle className="w-10 h-10 text-red-500" />
          </div>
        ) : yellow_alert ? (
          <div className="flex items-center justify-center">
            <AlertTriangle className="w-10 h-10 text-yellow-500" />
          </div>
        ) : !image_url ? (
          <div className="flex items-center justify-center">
            <ImageOff className="w-10 h-10 text-gray-500" />
          </div>
        ) : (
          <Image
            url={image_url}
            thumbnail={image_url}
            image_dims={image_dims}
            thumbnail_dims={image_dims}
          />
        )}
        {/* Details */}
        <div className="flex flex-col gap-2">
          <Row label="Measurements" value={measurements} />
          <Row label="Birthday" value={birthday} />
          <SeiyuuRow seiyuu={seiyuu} />
          <TraitsRow traits={traits} showSexual={sexualLevel === "explicit"} spoilerLevel={parseInt(spoilerLevel)} />
          <DescriptionRow description={description} />
        </div>
      </div>
    </div>
  )
}
