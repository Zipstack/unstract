class OrgIdNotValid(APIException):
    status_code = 400
    default_detail = "Organization ID is not valid"