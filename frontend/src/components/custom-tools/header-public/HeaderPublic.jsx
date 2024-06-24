import './HeaderPublic.css';
import logo from '../../../assets/Unstract.svg';

function HeaderPublic({}) {
  return (
    <div className="custom-tools-header-layout-public">
      <img src={logo} alt="Logo" className="public-logo" />
    </div>
  );
}
export { HeaderPublic };
