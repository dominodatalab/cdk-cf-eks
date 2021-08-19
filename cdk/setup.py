import setuptools

from domino_cdk import __version__

with open("README.md") as fp:
    long_description = fp.read()


setuptools.setup(
    name="domino-cdk",
    version=__version__,
    description="Domino CDK Stacks",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Domino Data Lab",
    packages=[
        "domino_cdk",
        "domino_cdk.config",
        "domino_cdk.provisioners",
        "domino_cdk.provisioners.eks",
        "domino_cdk.provisioners.lambda_files",
    ],
    package_data={"domino_cdk": ["config_template.yaml"]},
    data_files=[
        ("domino-cdk", ["app.py", "cdk.json", "util.py"]),
    ],
    install_requires=[
        "aws-cdk.assertions~=1.110.1",
        "aws-cdk.aws-backup~=1.110.1",
        "aws-cdk.aws-ec2~=1.110.1",
        "aws-cdk.aws-ecr~=1.110.1",
        "aws-cdk.aws-efs~=1.110.1",
        "aws-cdk.aws-eks~=1.110.1",
        "aws-cdk.aws-iam~=1.110.1",
        "aws-cdk.aws-lambda~=1.110.1",
        "aws-cdk.aws-s3~=1.110.1",
        "aws-cdk.aws-stepfunctions-tasks~=1.110.1",
        "aws-cdk.core~=1.110.1",
        "aws-cdk.lambda-layer-awscli~=1.110.1",
        "aws-cdk.lambda-layer-kubectl~=1.110.1",
        "boto3~=1.18.7",
        "field_properties~=0.1",
        "requests~=2.25.1",
        "ruamel.yaml~=0.17.7",
        "semantic_version~=2.8.5",
    ],
    python_requires=">=3.6",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: Apache Software License",
        "Programming Language :: JavaScript",
        "Programming Language :: Python :: 3 :: Only",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Topic :: Software Development :: Code Generators",
        "Topic :: Utilities",
        "Typing :: Typed",
    ],
)
