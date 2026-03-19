import { useCallback, useRef, useState } from "react";

function useListSearch(searchField) {
  const listRef = useRef([]);
  const searchTextRef = useRef("");
  const [displayList, setDisplayList] = useState([]);

  const filterList = useCallback(
    (list, searchText) => {
      if (!searchText.trim()) {
        return list;
      }
      return list.filter((item) =>
        item[searchField]?.toLowerCase().includes(searchText.toLowerCase()),
      );
    },
    [searchField],
  );

  const setMasterList = useCallback(
    (list) => {
      listRef.current = list;
      setDisplayList(filterList(list, searchTextRef.current));
    },
    [filterList],
  );

  const onSearch = useCallback(
    (searchText, setSearchList) => {
      searchTextRef.current = searchText;
      setSearchList(filterList(listRef.current, searchText));
    },
    [filterList],
  );

  const clearSearch = useCallback(() => {
    searchTextRef.current = "";
    setDisplayList(listRef.current);
  }, []);

  const updateMasterList = useCallback(
    (updateFn) => {
      const updatedList = updateFn(listRef.current);
      listRef.current = updatedList;
      setDisplayList(filterList(updatedList, searchTextRef.current));
    },
    [filterList],
  );

  return {
    listRef,
    displayList,
    setDisplayList,
    setMasterList,
    updateMasterList,
    onSearch,
    clearSearch,
  };
}

export { useListSearch };
