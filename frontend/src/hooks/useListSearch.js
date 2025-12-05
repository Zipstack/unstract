import { useRef, useState, useCallback } from "react";

function useListSearch(searchField) {
  const listRef = useRef([]);
  const [displayList, setDisplayList] = useState([]);

  const setMasterList = useCallback((list) => {
    listRef.current = list;
    setDisplayList(list);
  }, []);

  const onSearch = useCallback(
    (searchText, setSearchList) => {
      if (!searchText.trim()) {
        setSearchList(listRef.current);
        return;
      }
      const filteredList = listRef.current.filter((item) =>
        item[searchField]?.toLowerCase().includes(searchText.toLowerCase())
      );
      setSearchList(filteredList);
    },
    [searchField]
  );

  const updateMasterList = useCallback((updateFn) => {
    const updatedList = updateFn(listRef.current);
    listRef.current = updatedList;
    setDisplayList(updatedList);
  }, []);

  return {
    listRef,
    displayList,
    setDisplayList,
    setMasterList,
    updateMasterList,
    onSearch,
  };
}

export { useListSearch };
