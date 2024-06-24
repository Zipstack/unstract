import { useRef, useEffect, useState } from "react";
import * as pdfjsLib from "pdfjs-dist/webpack";
import PropTypes from "prop-types";

// Specify the worker source
pdfjsLib.GlobalWorkerOptions.workerSrc = `//cdnjs.cloudflare.com/ajax/libs/pdf.js/${pdfjsLib.version}/pdf.worker.min.js`;

const PDFViewer = ({ pdfUrl }) => {
  const canvasRef = useRef(null);
  const [numPages, setNumPages] = useState(null);
  const [currentPage, setCurrentPage] = useState(1);

  useEffect(() => {
    const renderTask = async () => {
      try {
        const loadingTask = pdfjsLib.getDocument(require("./input.pdf"));
        const pdf = await loadingTask.promise;
        setNumPages(pdf.numPages);

        // Render initial page
        renderPage(pdf, currentPage);
      } catch (error) {
        console.log("Error occurred while rendering the PDF:", error);
      }
    };

    renderTask();
  }, [pdfUrl, currentPage]);

  const renderPage = async (pdf, pageNumber) => {
    try {
      const page = await pdf.getPage(pageNumber);

      // Prepare canvas using PDF page dimensions
      const canvas = canvasRef.current;
      const context = canvas.getContext("2d");
      const viewport = page.getViewport({ scale: 1.5 });
      canvas.height = viewport.height;
      canvas.width = viewport.width;

      // Render PDF page into canvas context
      const renderContext = {
        canvasContext: context,
        viewport: viewport,
      };
      await page.render(renderContext).promise;
    } catch (error) {
      console.log("Error occurred while rendering the page:", error);
    }
  };

  const handleScroll = (e) => {
    const container = e.target;
    const scrollRatio = container.scrollTop / container.scrollHeight;
    const nextPage = Math.ceil(scrollRatio * numPages);
    setCurrentPage(nextPage);
  };

  return (
    <div style={{ overflow: "auto", height: "800px" }} onScroll={handleScroll}>
      {Array.from({ length: numPages }, (_, index) => index + 1).map((page) => (
        <div key={page} style={{ marginBottom: "16px" }}>
          {page === currentPage && <canvas ref={canvasRef} />}
        </div>
      ))}
    </div>
  );
};

PDFViewer.propTypes = {
  pdfUrl: PropTypes.string.isRequired,
};

export default PDFViewer;
