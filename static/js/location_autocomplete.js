
document.addEventListener("DOMContentLoaded", () => {
    const searchInput = document.getElementById("location-search");
    const resultsList = document.getElementById("location-results");

    if (!searchInput || !resultsList) {
        return;
    }

    let debounceTimer;
    let activeController;

    function hideResults() {
        resultsList.replaceChildren();
        resultsList.classList.add("hidden");
    }

    searchInput.addEventListener("input", () => {
        const query = searchInput.value.trim();

        clearTimeout(debounceTimer);

        if (activeController) {
            activeController.abort();
        }

        hideResults();

        if (query.length < 2) {
            return;
        }

        debounceTimer = setTimeout(async () => {
            activeController = new AbortController();

            try {
                const response = await fetch(
                    `/api/autocomplete/?q=${encodeURIComponent(query)}`,
                    { signal: activeController.signal }
                );

                if (!response.ok) {
                    throw new Error("Autocomplete request failed");
                }

                const locations = await response.json();

                if (searchInput.value.trim() !== query) {
                    return;
                }

                resultsList.replaceChildren();

                locations.forEach((location) => {
                    const item = document.createElement("li");
                    const option = document.createElement("button");

                    option.type = "button";
                    option.className =
                        "block w-full px-4 py-3 text-left text-gray-800 hover:bg-indigo-50";

                    option.textContent =
                        `${location.name} (${location.country})`;

                    option.addEventListener("click", () => {
                        searchInput.value = location.name;
                        hideResults();
                    });

                    item.appendChild(option);
                    resultsList.appendChild(item);
                });

                if (locations.length > 0) {
                    resultsList.classList.remove("hidden");
                }
            } catch (error) {
                if (error.name !== "AbortError") {
                    console.error("Location autocomplete error:", error);
                }
            }
        }, 300);
    });

    document.addEventListener("click", (event) => {
        if (
            !searchInput.contains(event.target) &&
            !resultsList.contains(event.target)
        ) {
            hideResults();
        }
    });
});
