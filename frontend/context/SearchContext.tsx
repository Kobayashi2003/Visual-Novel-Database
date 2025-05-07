"use client"

import { createContext, useContext, useState, useEffect } from "react"

interface SearchContextType {
  searchFrom: string
  searchType: string
  sortBy: string
  setSearchFrom: (from: string) => void
  setSearchType: (type: string) => void
  setSortBy: (by: string) => void
}

const SearchContext = createContext<SearchContextType | undefined>(undefined)

export function useSearchContext() {
  const context = useContext(SearchContext)
  if (context === undefined) {
    throw new Error("useSearchContext must be used within a SearchProvider")
  }
  return context
}

export function SearchProvider({ children }: { children: React.ReactNode}) {
  const [searchFrom, setSearchFromTemp] = useState<string>("both")
  const [searchType, setSearchTypeTemp] = useState<string>("v")
  const [sortBy, setSortByTemp] = useState<string>("id")

  const setSearchFrom = (from: string) => {
    setSearchFromTemp(from)
    localStorage.setItem("searchFrom", from)
  }

  const setSearchType= (type: string) => {
    setSearchTypeTemp(type)
    localStorage.setItem("searchType", type)
  }

  const setSortBy = (by: string) => {
    setSortByTemp(by)
    localStorage.setItem(`sortBy-${searchType}-${searchFrom}`, by)
  }


  useEffect(() => {
    const searchFrom = localStorage.getItem("searchFrom") || "both"
    const searchType = localStorage.getItem("searchType") || "v"
    const sortBy = localStorage.getItem(`sortBy-${searchType}-${searchFrom}`) || "id"
    setSearchFromTemp(searchFrom)
    setSearchTypeTemp(searchType)
    setSortByTemp(sortBy)
  }, [])
  
  useEffect(() => {
    const sortBy = localStorage.getItem(`sortBy-${searchType}-${searchFrom}`) || "id"
    setSortByTemp(sortBy)
  }, [searchFrom, searchType])

  return (
    <SearchContext.Provider value={{ searchFrom, searchType, sortBy, setSearchFrom, setSearchType, setSortBy }}>
      {children}
    </SearchContext.Provider>
  )
}
