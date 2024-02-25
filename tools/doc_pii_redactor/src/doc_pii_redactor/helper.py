import json
import re
from typing import Any

import boto3
from unstract.sdk.constants import LogLevel
from unstract.sdk.tool.base import BaseTool
from unstract.sdk.utils import ToolUtils

from .enums import Processor


class PIIRedactHelper:
    AMAZON_COMPREHEND_TYPE_MAPPING = {
        "Address": "ADDRESS",
        "Age": "AGE",
        "Bank Account Number": "BANK_ACCOUNT_NUMBER",
        "Bank Routing Number": "BANK_ROUTING",
        "Canada Health Number": "CA_HEALTH_NUMBER",
        "Canada Social Insurance Number": "CA_SOCIAL_INSURANCE_NUMBER",
        "Credit Card Number": "CREDIT_DEBIT_NUMBER",
        "Credit Card CVV": "CREDIT_DEBIT_CVV",
        "Credit Card Expiration Date": "CREDIT_DEBIT_EXPIRY",
        "Date & Time": "DATE_TIME",
        "Email": "EMAIL",
        "Indian Aadhaar Number": "IN_AADHAAR",
        "Indian PAN Number": "IN_PERMANENT_ACCOUNT_NUMBER",
        "Indian NREGA Number": "IN_NREGA",
        "Indian Voter ID Number": "IN_VOTER_NUMBER",
        "IP Address": "IP_ADDRESS",
        "MAC Address": "MAC_ADDRESS",
        "Name": "NAME",
        "Passport Number": "PASSPORT_NUMBER",
        "Password": "PASSWORD",
        "Phone Number": "PHONE",
        "PIN": "PIN",
        "SSN": "SSN",
        "URL": "URL",
        "UK National Insurance Number": "UK_NATIONAL_INSURANCE_NUMBER",
        "UK NHS Number": "UK_NATIONAL_HEALTH_SERVICE_NUMBER",
        "UK Tax ID Number": "UK_UNIQUE_TAXPAYER_REFERENCE_NUMBER",
        "US Individual Taxpayer Identification Number": "US_INDIVIDUAL_TAX_IDENTIFICATION_NUMBER",  # noqa
        "Username": "USERNAME",
        "VIN": "VEHICLE_IDENTIFICATION_NUMBER",
    }

    def __init__(self, tool: BaseTool) -> None:
        self.tool = tool

    def get_cache_key(
        self, workflow_id: str, settings: dict[str, Any], input_text: str
    ) -> str:
        """Returns a unique cache key for an input.

        Args:
            workflow_id (str): UUID for a project
            settings (dict): Tool settings
            input_text (str): Text from the file read

        Returns:
            str: Unique key to set or get from cache
        """
        input_text_hash = ToolUtils.hash_str(input_text)
        settings_hash = ToolUtils.hash_str(json.dumps(settings))
        return f"cache:{workflow_id}:{settings_hash}:{input_text_hash}"

    @staticmethod
    def create_redaction_overlay(text: str) -> str:
        return "x" * len(text)

    def detect_pii_entities(
        self,
        text: str,
        processor: str,
        redact_items: list[str],
        score_threshold: float,
    ) -> list[str]:
        """Detects PII entites to be redacted.

        Types of PII entities: https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/comprehend/client/detect_pii_entities.html  # noqa
        'BANK_ACCOUNT_NUMBER | 'BANK_ROUTING' | 'CREDIT_DEBIT_NUMBER' |
        'CREDIT_DEBIT_CVV' | 'CREDIT_DEBIT_EXPIRY' | 'PIN' | 'EMAIL' | 'ADDRESS' | 'NAME' | 'PHONE' | 'SSN' | # noqa
        'DATE_TIME' | 'PASSPORT_NUMBER' | 'DRIVER_ID' | 'URL' | 'AGE' | 'USERNAME' | 'PASSWORD' | 'AWS_ACCESS_KEY' | # noqa
        'AWS_SECRET_KEY' | 'IP_ADDRESS' | 'MAC_ADDRESS' | 'ALL' | 'LICENSE_PLATE' | 'VEHICLE_IDENTIFICATION_NUMBER' | # noqa
        'UK_NATIONAL_INSURANCE_NUMBER' | 'CA_SOCIAL_INSURANCE_NUMBER' | 'US_INDIVIDUAL_TAX_IDENTIFICATION_NUMBER' | # noqa
        'UK_UNIQUE_TAXPAYER_REFERENCE_NUMBER' | 'IN_PERMANENT_ACCOUNT_NUMBER' | 'IN_NREGA' | # noqa
        'INTERNATIONAL_BANK_ACCOUNT_NUMBER' | 'SWIFT_CODE' | 'UK_NATIONAL_HEALTH_SERVICE_NUMBER' | 'CA_HEALTH_NUMBER' | # noqa
        'IN_AADHAAR' | 'IN_VOTER_NUMBER'

        Args:
            text (str): Input text to check
            processor (str): The processor that has to be used
            redact_items (list[str]): Elements to be redacted
            score_threshold (float): The confidence used to decide if entity is PII

        Returns:
            list[str]: List of entities to be redacted
        """
        if processor == Processor.AMAZON_COMPREHEND.value:
            aws_region_name = self.tool.get_env_or_die("PII_REDACT_AWS_REGION")
            access_key = self.tool.get_env_or_die(
                "PII_REDACT_AWS_ACCESS_KEY_ID"
            )
            secret_key = self.tool.get_env_or_die(
                "PII_REDACT_AWS_SECRET_ACCESS_KEY"
            )

            try:
                comprehend = boto3.client(
                    "comprehend",
                    aws_access_key_id=access_key,
                    aws_secret_access_key=secret_key,
                    region_name=aws_region_name,
                )
                response = comprehend.detect_pii_entities(
                    Text=text, LanguageCode="en"
                )
            except Exception as e:
                self.tool.stream_log(
                    f"Error detecting PII elements: {e}", LogLevel.ERROR
                )
                exit(1)
            else:
                mapped_redact_items = []
                for item in redact_items:
                    if item in self.AMAZON_COMPREHEND_TYPE_MAPPING:
                        mapped_redact_items.append(
                            self.AMAZON_COMPREHEND_TYPE_MAPPING[item]
                        )
                    else:
                        mapped_redact_items.append(item)
                self.tool.stream_log(f"Redact items: {mapped_redact_items}")

                pii_entities = response["Entities"]
                pii_texts = []
                for entity in pii_entities:
                    if entity["Score"] < score_threshold:
                        continue
                    if len(mapped_redact_items) > 0:
                        if entity["Type"] not in mapped_redact_items:
                            continue
                    start = entity["BeginOffset"]
                    end = entity["EndOffset"]
                    redact_text = text[start:end]
                    redact_text = redact_text.replace("\n", "")
                    redact_text = redact_text.strip()
                    if redact_text not in pii_texts:
                        pii_texts.append(redact_text)

                # Remove multiple spaces in the strings with a single space
                items_to_redact = [
                    re.sub(" +", " ", item) for item in pii_texts
                ]
                items_to_redact = sorted(items_to_redact, key=len, reverse=True)
                return items_to_redact
        else:
            return []
