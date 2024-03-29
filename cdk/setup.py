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
        "aws-cdk-lib~=2.95.0",
        "aws-cdk.lambda-layer-kubectl-v24~=2.0.242",
        "aws-cdk.lambda-layer-kubectl-v25~=2.0.4",
        "aws-cdk.lambda-layer-kubectl-v26~=2.0.1",
        "boto3~=1.26.0",
        "field_properties~=0.1",
        "requests~=2.28.1",
        "ruamel.yaml~=0.17.21",
        "semantic_version~=2.10.0",
    ],
    python_requires=">=3.9",
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
