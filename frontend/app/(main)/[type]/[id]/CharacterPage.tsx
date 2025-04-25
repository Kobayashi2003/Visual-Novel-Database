"use client"

import { useState } from "react"

import { Character } from "@/lib/types"

import { SpoilerLevelSelector } from "@/components/selector/SpoilerLevelSelector"
import { SexualLevelSelector } from "@/components/selector/SexualLevelSelector"
import { ViolenceLevelSelector } from "@/components/selector/ViolenceLevelSelector"

import { CharacterDetailsPanel } from "@/components/panel/CharacterDetailsPanel"

interface CharacterPageProps {
  character: Character
}

export default function CharacterPage({ character }: CharacterPageProps) {

  const [spoilerLevel, setSpoilerLevel] = useState<"0" | "1" | "2">("0")
  const [sexualLevel, setSexualLevel] = useState<"safe" | "suggestive" | "explicit">("safe")
  const [violenceLevel, setViolenceLevel] = useState<"tame" | "violent" | "brutal">("tame")

  return (
    <div className="flex flex-col gap-4">
      <div className="w-full flex flex-col xl:flex-row xl:justify-around gap-1">
        <SpoilerLevelSelector
          spoilerLevel={spoilerLevel}
          setSpoilerLevel={(value) => setSpoilerLevel(value as "0" | "1" | "2")}
          className="max-xl:w-full xl:flex-1 not-italic"
        />
        <SexualLevelSelector
          sexualLevel={sexualLevel}
          setSexualLevel={(value) => setSexualLevel(value as "safe" | "suggestive" | "explicit")}
          className="max-xl:w-full xl:flex-1 not-italic"
        />
        <ViolenceLevelSelector
          violenceLevel={violenceLevel}
          setViolenceLevel={(value) => setViolenceLevel(value as "tame" | "violent" | "brutal")}
          className="max-xl:w-full xl:flex-1 not-italic"
        />
      </div>
      <CharacterDetailsPanel character={character} spoilerLevel={spoilerLevel} sexualLevel={sexualLevel} violenceLevel={violenceLevel} />
    </div>
  )
}
