// Import SVGs as URLs and create React components
import sunIconUrl from "./sun-icon.svg";
import moonIconUrl from "./moon-icon.svg";
import logo64Url from "./logo-64.svg";
import logo24Url from "./logo-24.svg";
import documentUrl from "./document.svg";
import folderUrl from "./folder.svg";
import bingAdsUrl from "./BingAds.svg";
import toolIconUrl from "./tool.svg";
import inputPlaceholderUrl from "./input-placeholder.svg";
import outputPlaceholderUrl from "./output-placeholder.svg";
import toolIdeInputDocPlaceholderUrl from "./tool-ide-input-document-placeholder.svg";
import toolIdePromptsPlaceholderUrl from "./tool-ide-prompts-placeholder.svg";
import unstractLogoUrl from "./Unstract.svg";
import listOfWfStepsPlaceholderUrl from "./list-of-wf-steps-placeholder.svg";
import listOfToolsPlaceholderUrl from "./list-of-tools-placeholder.svg";
import apiDeploymentsUrl from "./api-deployments.svg";
import workflowsUrl from "./Workflows.svg";
import taskUrl from "./task.svg";
import stepIconUrl from "./steps.svg";
import combinedOutputIconUrl from "./combined-output.svg";
import emptyPlaceholderUrl from "./empty.svg";
import desktopUrl from "./desktop.svg";
import reachOutUrl from "./reach-out.svg";
import requireDemoIconUrl from "./require-demo.svg";
import learnMoreUrl from "./learn-more.svg";
import unstractBlackLogoUrl from "./UnstractLogoBlack.svg";
import squareBgUrl from "./square-bg.svg";
import trialDocUrl from "./trial-doc.svg";
import textExtractorIconUrl from "./text-extractor.svg";
import ocrIconUrl from "./ocr.svg";
import orgAvatarUrl from "./org-selection-avatar.svg";
import orgSelectionUrl from "./org-selection.svg";
import redGradCircleUrl from "./red-grad-circle.svg";
import yellowGradCircleUrl from "./yellow-grad-circle.svg";
import exportToolIconUrl from "./export-tool.svg";
import placeholderImgUrl from "./placeholder.svg";
import customToolIconUrl from "./custom-tools-icon.svg";
import etlIconUrl from "./etl.svg";

// Create React components from SVG URLs
const createSvgComponent = (url, name) => (props) => (
  <img src={url} alt={name} {...props} />
);

const SunIcon = createSvgComponent(sunIconUrl, 'Sun Icon');
const MoonIcon = createSvgComponent(moonIconUrl, 'Moon Icon');
const Logo64 = createSvgComponent(logo64Url, 'Logo 64');
const Logo24 = createSvgComponent(logo24Url, 'Logo 24');
const Document = createSvgComponent(documentUrl, 'Document');
const Folder = createSvgComponent(folderUrl, 'Folder');
const BingAds = createSvgComponent(bingAdsUrl, 'Bing Ads');
const ToolIcon = createSvgComponent(toolIconUrl, 'Tool Icon');
const InputPlaceholder = createSvgComponent(inputPlaceholderUrl, 'Input Placeholder');
const OutputPlaceholder = createSvgComponent(outputPlaceholderUrl, 'Output Placeholder');
const ToolIdeInputDocPlaceholder = createSvgComponent(toolIdeInputDocPlaceholderUrl, 'Tool IDE Input Doc Placeholder');
const ToolIdePromptsPlaceholder = createSvgComponent(toolIdePromptsPlaceholderUrl, 'Tool IDE Prompts Placeholder');
const UnstractLogo = createSvgComponent(unstractLogoUrl, 'Unstract Logo');
const ListOfWfStepsPlaceholder = createSvgComponent(listOfWfStepsPlaceholderUrl, 'List of WF Steps Placeholder');
const ListOfToolsPlaceholder = createSvgComponent(listOfToolsPlaceholderUrl, 'List of Tools Placeholder');
const ApiDeployments = createSvgComponent(apiDeploymentsUrl, 'API Deployments');
const Workflows = createSvgComponent(workflowsUrl, 'Workflows');
const Task = createSvgComponent(taskUrl, 'Task');
const StepIcon = createSvgComponent(stepIconUrl, 'Step Icon');
const CombinedOutputIcon = createSvgComponent(combinedOutputIconUrl, 'Combined Output Icon');
const EmptyPlaceholder = createSvgComponent(emptyPlaceholderUrl, 'Empty Placeholder');
const Desktop = createSvgComponent(desktopUrl, 'Desktop');
const ReachOut = createSvgComponent(reachOutUrl, 'Reach Out');
const RequireDemoIcon = createSvgComponent(requireDemoIconUrl, 'Require Demo Icon');
const LearnMore = createSvgComponent(learnMoreUrl, 'Learn More');
const UnstractBlackLogo = createSvgComponent(unstractBlackLogoUrl, 'Unstract Black Logo');
const SquareBg = createSvgComponent(squareBgUrl, 'Square Background');
const TrialDoc = createSvgComponent(trialDocUrl, 'Trial Doc');
const TextExtractorIcon = createSvgComponent(textExtractorIconUrl, 'Text Extractor Icon');
const OcrIcon = createSvgComponent(ocrIconUrl, 'OCR Icon');
const OrgAvatar = createSvgComponent(orgAvatarUrl, 'Org Avatar');
const OrgSelection = createSvgComponent(orgSelectionUrl, 'Org Selection');
const RedGradCircle = createSvgComponent(redGradCircleUrl, 'Red Grad Circle');
const YellowGradCircle = createSvgComponent(yellowGradCircleUrl, 'Yellow Grad Circle');
const ExportToolIcon = createSvgComponent(exportToolIconUrl, 'Export Tool Icon');
const PlaceholderImg = createSvgComponent(placeholderImgUrl, 'Placeholder Image');
const CustomToolIcon = createSvgComponent(customToolIconUrl, 'Custom Tool Icon');
const ETLIcon = createSvgComponent(etlIconUrl, 'ETL Icon');

export {
  SunIcon,
  MoonIcon,
  Logo64,
  Logo24,
  Document,
  Folder,
  BingAds,
  ToolIcon,
  InputPlaceholder,
  OutputPlaceholder,
  ToolIdeInputDocPlaceholder,
  ToolIdePromptsPlaceholder,
  UnstractLogo,
  ListOfWfStepsPlaceholder,
  ListOfToolsPlaceholder,
  ApiDeployments,
  Workflows,
  StepIcon,
  EmptyPlaceholder,
  CombinedOutputIcon,
  Desktop,
  ReachOut,
  RequireDemoIcon,
  LearnMore,
  UnstractBlackLogo,
  SquareBg,
  TrialDoc,
  TextExtractorIcon,
  OcrIcon,
  OrgAvatar,
  OrgSelection,
  RedGradCircle,
  YellowGradCircle,
  ExportToolIcon,
  PlaceholderImg,
  CustomToolIcon,
  ETLIcon,
  Task,
};
